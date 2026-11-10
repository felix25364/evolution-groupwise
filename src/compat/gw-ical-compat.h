/* SPDX-License-Identifier: LGPL-2.1-or-later */
#pragma once

#include <libical-glib/libical-glib.h>

#if ICAL_MAJOR_VERSION >= 4
#define i_cal_trigger_new_from_int i_cal_trigger_new_from_seconds
#define i_cal_duration_as_int i_cal_duration_as_seconds
#define ICalProperty_Class ICalPropertyClassenum
#endif

/* Return only actual BY values: libical 3 arrays include a sentinel,
 * whereas libical 4 arrays are sized to the number of values. */
#if ICAL_MAJOR_VERSION < 4
static inline GArray *
gw_recurrence_trim_array (GArray *array)
{
	guint length = 0;

	while (array && length < array->len &&
	       g_array_index (array, gshort, length) != I_CAL_RECURRENCE_ARRAY_MAX)
		length++;
	if (array)
		g_array_set_size (array, length);
	return array;
}
#endif

static inline GArray *
gw_recurrence_get_by_set_pos_array (ICalRecurrence *rule)
{
#if ICAL_MAJOR_VERSION >= 4
	return i_cal_recurrence_get_by_array (rule, I_CAL_BY_SET_POS);
#else
	return gw_recurrence_trim_array (i_cal_recurrence_get_by_set_pos_array (rule));
#endif
}

static inline GArray *
gw_recurrence_get_by_day_array (ICalRecurrence *rule)
{
#if ICAL_MAJOR_VERSION >= 4
	return i_cal_recurrence_get_by_array (rule, I_CAL_BY_DAY);
#else
	return gw_recurrence_trim_array (i_cal_recurrence_get_by_day_array (rule));
#endif
}

static inline GArray *
gw_recurrence_get_by_month_day_array (ICalRecurrence *rule)
{
#if ICAL_MAJOR_VERSION >= 4
	return i_cal_recurrence_get_by_array (rule, I_CAL_BY_MONTH_DAY);
#else
	return gw_recurrence_trim_array (i_cal_recurrence_get_by_month_day_array (rule));
#endif
}

static inline GArray *
gw_recurrence_get_by_year_day_array (ICalRecurrence *rule)
{
#if ICAL_MAJOR_VERSION >= 4
	return i_cal_recurrence_get_by_array (rule, I_CAL_BY_YEAR_DAY);
#else
	return gw_recurrence_trim_array (i_cal_recurrence_get_by_year_day_array (rule));
#endif
}

static inline GArray *
gw_recurrence_get_by_month_array (ICalRecurrence *rule)
{
#if ICAL_MAJOR_VERSION >= 4
	return i_cal_recurrence_get_by_array (rule, I_CAL_BY_MONTH);
#else
	return gw_recurrence_trim_array (i_cal_recurrence_get_by_month_array (rule));
#endif
}
