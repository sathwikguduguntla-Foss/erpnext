import frappe
from frappe import _
from frappe.model.docstatus import DocStatus


def execute(filters=None):
	group_fieldname = None
	if filters and isinstance(filters, dict):
		group_fieldname = filters.pop("group_by", None)

	filters = frappe._dict(filters or {})
	columns = get_columns(filters, group_fieldname)
	data = get_data(filters, group_fieldname)
	message = None
	chart = None
	report_summary = None
	skip_total_row = 1 if group_fieldname else 0

	return columns, data, message, chart, report_summary, skip_total_row


def get_columns(filters, group_fieldname=None):
	group_columns = {
		"date": {
			"label": _("Date"),
			"fieldtype": "Date",
			"fieldname": "date",
			"width": 150,
		},
		"project": {
			"label": _("Project"),
			"fieldtype": "Link",
			"fieldname": "project",
			"options": "Project",
			"width": 200,
			"hidden": int(bool(filters.get("project"))),
		},
		"employee": {
			"label": _("Employee ID"),
			"fieldtype": "Link",
			"fieldname": "employee",
			"options": "Employee",
			"width": 200,
			"hidden": int(bool(filters.get("employee"))),
		},
	}

	columns = []
	if group_fieldname and group_fieldname in group_columns:
		columns.append(group_columns.get(group_fieldname))
		columns.extend(
			column for column in group_columns.values() if column.get("fieldname") != group_fieldname
		)
	else:
		columns.extend(group_columns.values())

	columns.extend(
		[
			{
				"label": _("Employee Name"),
				"fieldtype": "data",
				"fieldname": "employee_name",
				"hidden": 1,
			},
			{
				"label": _("Timesheet"),
				"fieldtype": "Link",
				"fieldname": "timesheet",
				"options": "Timesheet",
				"width": 150,
			},
			{"label": _("Working Hours"), "fieldtype": "Float", "fieldname": "hours", "width": 150},
			{
				"label": _("Billing Hours"),
				"fieldtype": "Float",
				"fieldname": "billing_hours",
				"width": 150,
			},
			{
				"label": _("Billing Amount"),
				"fieldtype": "Currency",
				"fieldname": "billing_amount",
				"width": 150,
			},
		]
	)

	return columns


def get_data(filters, group_fieldname=None):
	_filters = []
	if filters.get("employee"):
		_filters.append(("employee", "=", filters.get("employee")))
	if filters.get("project"):
		_filters.append(("Timesheet Detail", "project", "=", filters.get("project")))
	if filters.get("from_date"):
		_filters.append(("Timesheet Detail", "from_time", ">=", filters.get("from_date")))
	if filters.get("to_date"):
		_filters.append(("Timesheet Detail", "to_time", "<=", filters.get("to_date")))
	if not filters.get("include_draft_timesheets"):
		_filters.append(("docstatus", "=", DocStatus.submitted()))
	else:
		_filters.append(("docstatus", "in", (DocStatus.submitted(), DocStatus.draft())))

	data = frappe.get_list(
		"Timesheet",
		fields=[
			"name as timesheet",
			"`tabTimesheet`.employee",
			"`tabTimesheet`.employee_name",
			"`tabTimesheet Detail`.from_time as date",
			"`tabTimesheet Detail`.project",
			"`tabTimesheet Detail`.hours",
			"`tabTimesheet Detail`.billing_hours",
			"`tabTimesheet Detail`.billing_amount",
		],
		filters=_filters,
		order_by="`tabTimesheet Detail`.from_time",
	)

	if not group_fieldname:
		for row in data:
			row.pop("indent", None)
			row.pop("is_group", None)
		return data

	grouped_data = group_by(data, group_fieldname)
	return add_total_row(grouped_data, group_fieldname)


def add_total_row(grouped_data, group_fieldname):
	# Build the grand total ourselves from the group (subtotal) rows only,
	# since child rows already carry the same hours/billing values and would
	# double count if included too.
	total_hours = total_billing_hours = total_billing_amount = 0
	for row in grouped_data:
		if row.get("is_group"):
			total_hours += row.get("hours") or 0
			total_billing_hours += row.get("billing_hours") or 0
			total_billing_amount += row.get("billing_amount") or 0

	group_row_count = sum(1 for row in grouped_data if row.get("is_group"))
	# Skip the total row when there's only one group — its subtotal already
	# equals the grand total, so a separate row would just repeat it.
	if group_row_count <= 1:
		return grouped_data

	total_row = {
		"hours": total_hours,
		"billing_hours": total_billing_hours,
		"billing_amount": total_billing_amount,
		"indent": 0,
		"is_group": 0,
	}
	# Label the total row under whichever column is first (Date/Project/Employee)
	total_row[group_fieldname] = _("Total")

	grouped_data.append(total_row)
	return grouped_data


def group_by(data, fieldname):
	if not fieldname:
		return data

	groups = {}
	for row in data:
		groups.setdefault(row.get(fieldname), []).append(row)

	grouped_data = []
	for group in sorted(groups, key=lambda g: (g is None, g)):
		hours = billing_hours = billing_amount = 0
		child_rows = []
		for row in groups[group]:
			hours += row.get("hours") or 0
			billing_hours += row.get("billing_hours") or 0
			billing_amount += row.get("billing_amount") or 0

			_row = row.copy()
			_row[fieldname] = None
			_row["indent"] = 1
			_row["is_group"] = 0
			child_rows.append(_row)

		group_row = {
			fieldname: group,
			"hours": hours,
			"billing_hours": billing_hours,
			"billing_amount": billing_amount,
			"indent": 0,
			"is_group": 1,
		}
		if fieldname == "employee":
			group_row["employee_name"] = groups[group][0].get("employee_name")

		grouped_data.append(group_row)
		grouped_data.extend(child_rows)

	return grouped_data
