import React from 'react';
import { Field } from './ui';
import { PORTAL_ROLES } from '../utils/portalAccess';

export default function PortalChoice({ value, onChange, disabled = false }) {
  return <Field label="Log in to">
    <select value={value} disabled={disabled} onChange={event => onChange(event.target.value)}>
      {Object.entries(PORTAL_ROLES).map(([role, label]) => <option key={role} value={role}>{label} portal</option>)}
    </select>
  </Field>;
}
