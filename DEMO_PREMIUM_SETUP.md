# Demo Premium checkout

This is a prototype payment simulation. It does not contact a payment provider,
collect card details, charge money or start recurring billing.

## Enable it

Add this to the project-root `.env`, then restart the backend:

```dotenv
DEMO_PAYMENTS_ENABLED=1
```

It is enabled in Donovan's local `uiabo-vision` environment. Teammates must add
the setting to their own local environment. It defaults to disabled when absent.
Do not enable this route in a real paid service: it deliberately lets eligible
Free users obtain Premium for no charge.

## Try it in the app

1. Sign in with a verified, active **Free app account**.
2. Open **Premium** using the banner on Home.
3. Select **Continue to demo checkout**.
4. Review the simulated S$2.00 monthly price and the actual S$0.00 charge.
5. Select **Complete demo payment**, or **Cancel** to keep the Free account.
6. On success, Home shows Premium and its monthly allowance; image features unlock.

The upgrade stays active until the project team changes the account. There is no
subscription expiry or recurring payment simulation. Premium allowance resets
on the first day of each calendar month in Singapore time.

## Behaviour to verify

- Completing checkout grants 60 checks for the current calendar month.
- Cancelling makes no account change.
- Repeating checkout does not reset an existing Premium allowance.
- A network failure can be retried: one receipt is stored per account.
- Staff, suspended, deactivated and unverified accounts cannot upgrade.
- A running analysis must finish before a Free account upgrades.
- Disabling `DEMO_PAYMENTS_ENABLED` prevents further demo upgrades; it does not
  revoke already granted Premium membership.

The server commits the membership, allowance and zero-charge receipt together.
Receipts are stored in `demo_payments/{uid}` and removed during account deletion.
The client cannot supply a UID, membership role, allowance, price or card details.

## Report image and link results

Open a completed deepfake, image-context or link-safety result, including from
history. Expand **Report a problem with this result**, select a reason, describe
the problem and submit it. Reporting uses no allowance.

A Data Engineer opens **Incorrect-result reports** in the portal. The detail
page shows the result's own classification, explanation and relevant evidence.
Saved images can be loaded through the authenticated investigation endpoint.
Reported URLs remain plain text; the portal does not visit them.

Image scoring and image labels are unchanged. Failed checks cannot be reported
as incorrect verdicts because no completed verdict was produced.
