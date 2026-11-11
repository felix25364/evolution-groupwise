/* SPDX-License-Identifier: LGPL-2.1-or-later
 * Native Messaging adapter for the existing GroupWise SOAP core. */
#include <json-glib/json-glib.h>
#include <gio/gio.h>
#include <stdio.h>
#include <string.h>
#include <signal.h>
#include <math.h>
#include "e-gw-connection.h"
#include "e-gw-folder.h"
#include "e-gw-xml.h"

#define INPUT_MAX (256u * 1024u)
#define OUTPUT_MAX (1024u * 1024u)
#define MIME_MAX (16u * 1024u * 1024u)
#define CHUNK_MAX (128u * 1024u)

/* A hard cap applies while downloading, before allocating the next chunk. */
typedef struct { GOutputStream parent; GByteArray *data; } BoundedStream;
typedef struct { GOutputStreamClass parent; } BoundedStreamClass;
G_DEFINE_TYPE(BoundedStream, bounded_stream, G_TYPE_OUTPUT_STREAM)
static gssize bounded_write(GOutputStream *stream, const void *buffer, gsize size,
                            GCancellable *cancel, GError **error) {
    BoundedStream *self = (BoundedStream *)stream;
    if (size > MIME_MAX - self->data->len) {
        g_set_error_literal(error, G_IO_ERROR, G_IO_ERROR_NO_SPACE, "Message exceeds download limit");
        return -1;
    }
    g_byte_array_append(self->data, buffer, size);
    return size;
}
static void bounded_finalize(GObject *obj) {
    g_byte_array_unref(((BoundedStream *)obj)->data);
    G_OBJECT_CLASS(bounded_stream_parent_class)->finalize(obj);
}
static void bounded_stream_class_init(BoundedStreamClass *klass) {
    G_OUTPUT_STREAM_CLASS(klass)->write_fn = bounded_write;
    G_OBJECT_CLASS(klass)->finalize = bounded_finalize;
}
static void bounded_stream_init(BoundedStream *self) { self->data = g_byte_array_new(); }

static EGwConnection *connection;
static GBytes *mime_cache;
static gchar *mime_id;
static void clear_mime(void) {
    g_clear_pointer(&mime_cache, g_bytes_unref);
    g_clear_pointer(&mime_id, g_free);
}
static void disconnect_host(void) {
    /* Dropping the process closes the session transport; no blocking logout on EOF. */
    g_clear_object(&connection);
    clear_mime();
}
static JsonObject *object(void) { return json_object_new(); }
static void str(JsonObject *o, const char *key, const char *s) {
    json_object_set_string_member(o, key, s ? s : "");
}
static const char *string(JsonObject *o, const char *key) {
    JsonNode *n = json_object_get_member(o, key);
    if (!n || !JSON_NODE_HOLDS_VALUE(n) || json_node_get_value_type(n) != G_TYPE_STRING) return NULL;
    const char *v = json_node_get_string(n);
    return v && strlen(v) <= 4096 && *v ? v : NULL;
}
static gboolean integer(JsonObject *o, const char *key, gint64 fallback, gint64 min,
                        gint64 max, gint64 *out) {
    JsonNode *n = json_object_get_member(o, key);
    if (!n) { *out = fallback; return TRUE; }
    if (!JSON_NODE_HOLDS_VALUE(n) || json_node_get_value_type(n) != G_TYPE_INT64) return FALSE;
    *out = json_node_get_int(n);
    return *out >= min && *out <= max;
}
static gboolean boolean(JsonObject *o, const char *key, gboolean fallback, gboolean *out) {
    JsonNode *n = json_object_get_member(o, key);
    if (!n) { *out = fallback; return TRUE; }
    if (!JSON_NODE_HOLDS_VALUE(n) || json_node_get_value_type(n) != G_TYPE_BOOLEAN) return FALSE;
    *out = json_node_get_boolean(n); return TRUE;
}
static void error_response(JsonObject *out, const char *code, const char *message) {
    json_object_remove_member(out, "result");
    JsonObject *err = object(); str(err, "code", code); str(err, "message", message);
    json_object_set_boolean_member(out, "ok", FALSE);
    json_object_set_object_member(out, "error", err);
}
static void soap_error(JsonObject *out, GError *error) {
    /* Never relay server descriptions: they may contain private data. */
    const char *code = "SERVER_ERROR";
    if (error) {
        if (error->domain == G_IO_ERROR && error->code == G_IO_ERROR_NO_SPACE) code = "MESSAGE_TOO_LARGE";
        else if (error->code == E_GW_ERROR_INVALID_PASSWORD || error->code == E_GW_ERROR_UNKNOWN_USER) code = "AUTH_FAILED";
        else if (error->code == E_GW_ERROR_INVALID_SESSION || error->code == E_GW_ERROR_NOT_LOGGED_IN) code = "SESSION_EXPIRED";
        else if (error->code == E_GW_ERROR_ITEM_NOT_FOUND) code = "NOT_FOUND";
        else if (error->domain == G_IO_ERROR || error->code == E_GW_ERROR_CONNECTION) code = "NETWORK_ERROR";
    }
    error_response(out, code, "GroupWise operation failed");
}
static void xml_string(JsonObject *o, const char *name, xmlNode *item, const char *path) {
    g_autofree gchar *s = e_gw_xml_dup_text(item, path); str(o, name, s);
}
static const char *folder_role(EGwFolderType type) {
    switch (type) {
    case E_GW_FOLDER_TYPE_ROOT: return "root";
    case E_GW_FOLDER_TYPE_MAILBOX: return "inbox";
    case E_GW_FOLDER_TYPE_SENT_ITEMS: return "sent";
    case E_GW_FOLDER_TYPE_DRAFT: return "drafts";
    case E_GW_FOLDER_TYPE_TRASH: return "trash";
    case E_GW_FOLDER_TYPE_JUNK: return "junk";
    case E_GW_FOLDER_TYPE_QUERY: return "query";
    default: return "folder";
    }
}
typedef struct { JsonArray *items; guint offset, limit, seen; gboolean stopped; } Listing;
static gboolean list_item(xmlNode *item, gpointer data) {
    Listing *l = data;
    g_autofree gchar *type = e_gw_xml_dup_attr(item, "type");
    if (!type || !(g_str_has_suffix(type, "Mail") || g_str_has_suffix(type, "PhoneMessage"))) return TRUE;
    if (l->seen++ < l->offset) return TRUE;
    if (json_array_get_length(l->items) >= l->limit) { l->stopped = TRUE; return FALSE; }
    JsonObject *m = object();
    g_autofree gchar *raw = e_gw_xml_dup_text(item, "id");
    g_autofree gchar *id = e_gw_clean_id(raw);
    str(m, "id", id); xml_string(m, "subject", item, "subject");
    xml_string(m, "sender", item, "distribution/from/email");
    xml_string(m, "senderName", item, "distribution/from/displayName");
    xml_string(m, "recipients", item, "distribution/to");
    g_autofree gchar *date = e_gw_xml_dup_text(item, "delivered");
    if (!date || !*date) { g_free(date); date = e_gw_xml_dup_text(item, "created"); }
    str(m, "date", date);
    xml_string(m, "modified", item, "modified");
    json_object_set_int_member(m, "size", e_gw_xml_get_int(item, "size", 0));
    json_object_set_boolean_member(m, "read", e_gw_xml_get_bool(item, "status/read"));
    json_object_set_boolean_member(m, "replied", e_gw_xml_get_bool(item, "status/replied"));
    json_array_add_object_element(l->items, m); return TRUE;
}

static void dispatch(JsonObject *request, JsonObject *out) {
    const char *op = string(request, "op");
    g_autoptr(GError) error = NULL;
    JsonObject *result = object();
    json_object_set_object_member(out, "result", result);
    json_object_set_boolean_member(out, "ok", TRUE);
    if (!op) goto invalid;
    if (!strcmp(op, "ping")) {
        str(result, "version", "0.1.0"); json_object_set_int_member(result, "protocolVersion", 1);
        json_object_set_int_member(result, "maxMessageBytes", MIME_MAX);
        json_object_set_int_member(result, "maxChunkBytes", CHUNK_MAX); return;
    }
    if (!strcmp(op, "logout")) { disconnect_host(); return; }
    if (!strcmp(op, "login")) {
        const char *host = string(request, "host"), *user = string(request, "username"), *password = string(request, "password");
        gint64 port; gboolean tls;
        if (!host || !user || !password || strpbrk(host, "/:@?# \\\r\n\t") ||
            !integer(request, "port", E_GW_DEFAULT_PORT, 1, 65535, &port) ||
            !boolean(request, "tls", TRUE, &tls)) goto invalid;
        disconnect_host();
        connection = e_gw_connection_new(host, port, tls);
        e_gw_connection_set_timeout(connection, 30);
        /* No insecure-certificate switch. Plain HTTP is explicit for legacy POAs/tests. */
        if (!e_gw_connection_login_sync(connection, user, password, NULL, &error)) {
            soap_error(out, error); disconnect_host(); return;
        }
        str(result, "email", e_gw_connection_get_user_email(connection));
        str(result, "name", e_gw_connection_get_user_name(connection)); return;
    }
    if (strcmp(op, "listFolders") && strcmp(op, "listMessages") && strcmp(op, "getMessage") &&
        strcmp(op, "markRead") && strcmp(op, "deleteMessages") && strcmp(op, "moveMessages") && strcmp(op, "copyMessages")) {
        error_response(out, "UNSUPPORTED_OPERATION", "Unknown operation"); return;
    }
    if (!connection) { error_response(out, "NOT_LOGGED_IN", "Login is required"); return; }
    if (!strcmp(op, "listFolders")) {
        g_autoptr(GPtrArray) folders = e_gw_connection_get_folder_list_sync(connection, "folders", TRUE, NULL, &error);
        if (!folders) { soap_error(out, error); return; }
        JsonArray *array = json_array_new();
        json_object_set_array_member(result, "folders", array);
        for (guint i = 0; i < folders->len; i++) {
            EGwFolder *f = g_ptr_array_index(folders, i);
            if (f->is_calendar || f->type == E_GW_FOLDER_TYPE_CONTACTS || f->type == E_GW_FOLDER_TYPE_DOCUMENTS) continue;
            JsonObject *entry = object(); str(entry, "id", f->id); str(entry, "parentId", f->parent_id);
            str(entry, "name", f->name); str(entry, "role", folder_role(f->type));
            json_object_set_int_member(entry, "count", f->count);
            json_object_set_int_member(entry, "unread", f->unread_count);
            json_array_add_object_element(array, entry);
        }
        return;
    }
    if (!strcmp(op, "listMessages")) {
        const char *folder = string(request, "folderId"); gint64 offset, limit;
        if (!folder || !integer(request, "offset", 0, 0, 100000, &offset) || !integer(request, "limit", 100, 1, 200, &limit)) goto invalid;
        /* Verify membership: some POAs silently return an empty list for bad IDs. */
        g_autoptr(GPtrArray) folders = e_gw_connection_get_folder_list_sync(connection, "folders", TRUE, NULL, &error);
        if (!folders) { soap_error(out, error); return; }
        gboolean found = FALSE;
        for (guint i = 0; i < folders->len; i++) if (!strcmp(((EGwFolder *)g_ptr_array_index(folders, i))->id, folder)) found = TRUE;
        if (!found) { error_response(out, "NOT_FOUND", "Folder not found"); return; }
        Listing listing = {json_array_new(), offset, limit, 0, FALSE};
        json_object_set_array_member(result, "messages", listing.items);
        gboolean ok = e_gw_connection_foreach_item_sync(connection, folder, "default", NULL, 200, list_item, &listing, NULL, &error);
        if (!ok && !listing.stopped) { soap_error(out, error); return; }
        json_object_set_boolean_member(result, "hasMore", listing.stopped);
        json_object_set_int_member(result, "nextOffset", offset + json_array_get_length(listing.items)); return;
    }
    if (!strcmp(op, "getMessage")) {
        const char *id = string(request, "messageId"); gint64 offset, limit;
        if (!id || !integer(request, "offset", 0, 0, MIME_MAX, &offset) || !integer(request, "limit", CHUNK_MAX, 1, CHUNK_MAX, &limit)) goto invalid;
        if (!offset) {
            clear_mime();
            g_autoptr(EGwResponse) item = e_gw_connection_get_item_sync(connection, id, "default", NULL, &error);
            if (!item) { soap_error(out, error); return; }
            /* Prefer the original Internet MIME attachment, preserving its full structure. */
            xmlNode *node = e_gw_xml_find(e_gw_response_get_node(item), "item");
            xmlNode *attachments = e_gw_xml_find(node, "attachments");
            g_autofree gchar *original = NULL;
            for (xmlNode *a = e_gw_xml_first_child(attachments, "attachment"); a; a = e_gw_xml_next_sibling(a, "attachment")) {
                g_autofree gchar *name = e_gw_xml_dup_text(a, "name");
                if (!g_strcmp0(name, "Mime.822")) {
                    g_autofree gchar *raw = e_gw_xml_dup_text(a, "id");
                    original = e_gw_clean_id(raw); break;
                }
            }
            BoundedStream *stream = g_object_new(bounded_stream_get_type(), NULL);
            gboolean ok = e_gw_connection_download_sync(connection, original ? original : id, !original, G_OUTPUT_STREAM(stream), NULL, &error);
            if (ok) { mime_cache = g_bytes_new(stream->data->data, stream->data->len); mime_id = g_strdup(id); }
            g_object_unref(stream);
            if (!ok) { soap_error(out, error); return; }
        }
        if (!mime_cache || g_strcmp0(mime_id, id)) { error_response(out, "CACHE_MISS", "Restart download at offset zero"); return; }
        gsize size; const guint8 *bytes = g_bytes_get_data(mime_cache, &size);
        if ((guint64)offset > size) goto invalid;
        gsize count = MIN((gsize)limit, size - offset);
        g_autofree gchar *b64 = g_base64_encode(count ? bytes + offset : (const guint8 *)"", count);
        str(result, "data", b64); str(result, "encoding", "base64");
        json_object_set_int_member(result, "total", size);
        json_object_set_int_member(result, "nextOffset", offset + count);
        json_object_set_boolean_member(result, "done", offset + count == size); return;
    }
    /* One item per mutation keeps request bounds explicit and errors unambiguous. */
    const char *id = string(request, "messageId"), *folder = string(request, "folderId");
    const char *ids[] = {id, NULL}; gboolean ok = FALSE;
    if (!id) goto invalid;
    if (!strcmp(op, "markRead")) {
        gboolean read;
        if (!boolean(request, "read", TRUE, &read)) goto invalid;
        ok = e_gw_connection_mark_read_sync(connection, ids, read, NULL, &error);
    } else if (!strcmp(op, "deleteMessages")) {
        if (!folder) goto invalid;
        ok = e_gw_connection_remove_items_sync(connection, ids, folder, NULL, &error);
    } else {
        const char *destination = string(request, "destinationId");
        if (!destination || (!strcmp(op, "moveMessages") && !folder)) goto invalid;
        ok = e_gw_connection_move_items_sync(connection, ids, destination, !strcmp(op, "copyMessages") ? NULL : folder, NULL, &error);
    }
    clear_mime();
    if (!ok) soap_error(out, error);
    return;
invalid:
    error_response(out, "INVALID_REQUEST", "Invalid or missing operation arguments");
}

static gboolean write_all(const void *data, size_t size) {
    const unsigned char *p = data;
    while (size) { size_t n = fwrite(p, 1, size, stdout); if (!n) return FALSE; p += n; size -= n; }
    return TRUE;
}
static gboolean reply(JsonObject *out) {
    g_autoptr(JsonNode) root = json_node_new(JSON_NODE_OBJECT);
    json_node_set_object(root, out);
    g_autoptr(JsonGenerator) gen = json_generator_new(); json_generator_set_root(gen, root);
    gsize size; g_autofree gchar *data = json_generator_to_data(gen, &size);
    if (size > OUTPUT_MAX) {
        JsonObject *small = object();
        JsonNode *id = json_object_get_member(out, "id");
        if (id) json_object_set_member(small, "id", json_node_copy(id));
        error_response(small, "RESPONSE_TOO_LARGE", "Use smaller batches");
        gboolean ok = reply(small); json_object_unref(small); return ok;
    }
    guint32 length = size; /* Native Messaging uses native byte order. */
    return write_all(&length, sizeof length) && write_all(data, size) && fflush(stdout) == 0;
}
int main(void) {
    signal(SIGPIPE, SIG_IGN);
    /* Prevent library debug records from leaking SOAP content to the protocol/logs. */
    g_unsetenv("G_MESSAGES_DEBUG");
    for (;;) {
        guint32 size; size_t n = fread(&size, 1, sizeof size, stdin);
        if (!n && feof(stdin)) break;
        if (n != sizeof size || !size || size > INPUT_MAX) { disconnect_host(); return 2; }
        g_autofree gchar *input = g_malloc(size + 1);
        if (fread(input, 1, size, stdin) != size) { disconnect_host(); return 2; }
        input[size] = 0;
        g_autoptr(JsonParser) parser = json_parser_new();
        JsonObject *out = object();
        json_object_set_null_member(out, "id");
        if (memchr(input, 0, size) || !g_utf8_validate(input, size, NULL) || !json_parser_load_from_data(parser, input, size, NULL) ||
            !JSON_NODE_HOLDS_OBJECT(json_parser_get_root(parser))) {
            error_response(out, "INVALID_JSON", "Expected a JSON object");
        } else {
            JsonObject *request = json_node_get_object(json_parser_get_root(parser));
            const char *id = string(request, "id");
            if (!id || strlen(id) > 128) error_response(out, "INVALID_REQUEST", "A short string request id is required");
            else { str(out, "id", id); dispatch(request, out); }
        }
        /* Best effort overwrite of input (the library owns its session credentials). */
        memset(input, 0, size);
        gboolean ok = reply(out); json_object_unref(out);
        if (!ok) { disconnect_host(); return 0; }
    }
    disconnect_host(); return 0;
}
