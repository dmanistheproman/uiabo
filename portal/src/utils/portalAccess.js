export const PORTAL_ROLES = {
  data_engineer: 'Data Engineer',
  system_admin: 'System Admin',
};

export function isPortalRole(value) {
  return Object.hasOwn(PORTAL_ROLES, value);
}

// This preference controls navigation only. The API validates access afresh.
export function storedPortalChoice(storage) {
  try {
    const role = storage.getItem('uiabo.portalChoice');
    return isPortalRole(role) ? role : 'data_engineer';
  } catch { return 'data_engineer'; }
}

export function portalRoles(profile) {
  if (!profile) return [];
  const kind = profile.account_type || (['staff', 'data_engineer', 'system_admin'].includes(profile.role) ? 'staff' : 'app');
  if (kind !== 'staff') return [];
  const roles = Object.hasOwn(profile, 'operational_roles')
    ? profile.operational_roles : [profile.role];
  return Array.isArray(roles) ? [...new Set(roles.filter(isPortalRole))] : [];
}

export function validatePortalSession(session, userId, selectedRole) {
  if (!isPortalRole(selectedRole) || session?.portal_role !== selectedRole
      || session.profile?.uid !== userId || session.profile?.account_status !== 'active'
      || !portalRoles(session.profile).includes(selectedRole)) {
    throw new Error('Portal access could not be confirmed. Please sign in again.');
  }
  return session;
}
