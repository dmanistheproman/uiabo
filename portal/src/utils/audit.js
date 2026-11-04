export const AUDIT_ACTIONS = {
  provision_account: 'Provision staff access', change_roles: 'Change portal permissions',
  convert_staff_to_app: 'Convert former staff to app account',
  change_status: 'Suspend / restore account', review_feedback: 'Review feedback',
  investigate_report: 'Investigate result report', monitor_pipeline: 'Pipeline monitoring',
  portal_login: 'Check portal access', view_audit: 'View audit history',
  view_accounts: 'View accounts', view_feedback: 'View feedback', other: 'Other action',
};

export function auditDateRange(days, now = new Date()) {
  if (![1, 7, 30].includes(days)) throw new Error('Choose a supported date range.');
  return { from_time: new Date(now.getTime() - days * 86400000).toISOString(), to_time: now.toISOString() };
}
