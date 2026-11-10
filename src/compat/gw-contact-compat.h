/* SPDX-License-Identifier: LGPL-2.1-or-later */
#pragma once

#include <libebook-contacts/libebook-contacts.h>
#include <libedataserver/eds-version.h>

/* Preserve the SOAP backend's vCard 3.0 representation after EDS 3.60
 * added vCard 4.0 and changed the serialization signatures. */
static inline gchar *
gw_vcard_to_string (EVCard *vcard)
{
#if EDS_CHECK_VERSION(3, 60, 0)
	return e_vcard_convert_to_string (vcard, E_VCARD_VERSION_30);
#else
	return e_vcard_to_string (vcard, EVC_FORMAT_VCARD_30);
#endif
}

static inline gchar *
gw_contact_date_to_string (EContactDate *date)
{
#if EDS_CHECK_VERSION(3, 60, 0)
	return e_contact_date_to_string (date, E_VCARD_VERSION_30);
#else
	return e_contact_date_to_string (date);
#endif
}
