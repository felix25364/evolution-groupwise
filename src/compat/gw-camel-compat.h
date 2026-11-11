/* SPDX-License-Identifier: LGPL-2.1-or-later */
#pragma once

#include <camel/camel.h>
#include <libedataserver/eds-version.h>

/* Camel 3.58 moved summary ownership and searching to CamelStoreDB. */
#if EDS_CHECK_VERSION(3, 58, 0)
#define CamelMIRecord CamelStoreDBMessageRecord
#define camel_folder_summary_get_array camel_folder_summary_dup_uids
#define camel_folder_summary_free_array g_ptr_array_unref
#define camel_folder_summary_get_changed camel_folder_summary_dup_changed
#define camel_folder_get_uids camel_folder_dup_uids
#define camel_folder_free_uids(folder, uids) g_ptr_array_unref (uids)
#define camel_folder_search_free(folder, uids) g_ptr_array_unref (uids)
#define camel_folder_search_util_hash_message_id camel_search_util_hash_message_id
#define camel_db_delete_folder camel_store_db_delete_folder

static inline GPtrArray *
gw_folder_search_by_expression (CamelFolder *folder, const gchar *expression,
                                GCancellable *cancellable, GError **error)
{
	GPtrArray *uids = NULL;

	camel_folder_search_sync (folder, expression, &uids, cancellable, error);
	return uids;
}
#define camel_folder_search_by_expression gw_folder_search_by_expression
#endif

/* These convenience methods were removed in 3.58; message-info setters
 * also work on 3.52 and retain Camel's summary/change notifications. */
static inline void
gw_folder_set_message_user_flag (CamelFolder *folder, const gchar *uid,
                                 const gchar *name, gboolean value)
{
	CamelMessageInfo *info = camel_folder_get_message_info (folder, uid);

	if (info) {
		camel_message_info_set_user_flag (info, name, value);
		g_object_unref (info);
	}
}

static inline void
gw_folder_set_message_user_tag (CamelFolder *folder, const gchar *uid,
                                const gchar *name, const gchar *value)
{
	CamelMessageInfo *info = camel_folder_get_message_info (folder, uid);

	if (info) {
		camel_message_info_set_user_tag (info, name, value);
		g_object_unref (info);
	}
}

static inline gint
gw_folder_get_unread_message_count (CamelFolder *folder)
{
	CamelFolderSummary *summary = camel_folder_get_folder_summary (folder);

	return summary ? (gint) camel_folder_summary_get_unread_count (summary) : -1;
}
