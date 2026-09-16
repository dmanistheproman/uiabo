// Presentation only: never infer truth from a number or reverse uncertainty.
export function resultPresentation(result) {
  if (result.processing_status === 'failed') return {
    outcome: 'failed', title: 'We could not finish this check',
    meaning: 'There was a problem completing the check. This is not a result about whether the message is true.',
    action: 'Try again later. This failed check did not use your allowance.',
    icon: 'alert-circle', color: '#8D302A', background: '#FBEDEA',
  };
  const outcome = result.assessment_outcome || (result.checkable === false ? 'not_checkable' : {
    'Low Concern': 'supported', 'High Concern': 'contradicted',
    'Needs Caution': 'conflicting', 'Not Enough Information': 'insufficient_evidence',
  }[result.concern_label]) || 'insufficient_evidence';
  const presentations = {
    supported: {
      title: 'The sources support this claim',
      meaning: 'The information we found agrees with the claim that was checked.',
      action: 'Read the sources before sharing. An automated check can still make a mistake.',
      icon: 'check-circle', color: '#176347', background: '#EAF5EF',
    },
    contradicted: {
      title: 'This claim appears incorrect',
      meaning: 'The information we found contradicts an important part of this claim.',
      action: 'Do not share it as a fact. Read the sources to see what is different.',
      icon: 'alert-octagon', color: '#963128', background: '#FBEDEA',
    },
    conflicting: {
      title: 'The sources disagree',
      meaning: 'Some information supports the claim, while other information contradicts it.',
      action: 'Wait before sharing. Read both sides or check with the organisation involved.',
      icon: 'alert-triangle', color: '#795408', background: '#FFF5D9',
    },
    unsupported: {
      title: 'This claim is not confirmed',
      meaning: 'We found related official information, but it does not confirm this claim. That does not prove the claim is false.',
      action: 'Do not share it as a confirmed fact. Check the original official announcement.',
      icon: 'help-circle', color: '#795408', background: '#FFF5D9',
    },
    insufficient_evidence: {
      title: 'We could not confirm this',
      meaning: 'We did not find enough information to say whether this claim is true or false.',
      action: 'Wait before sharing. Check with the organisation named in the message.',
      icon: 'help-circle', color: '#795408', background: '#FFF5D9',
    },
    not_checkable: {
      title: 'This cannot be fact-checked',
      meaning: 'We could not identify a factual claim to check. The message may be an opinion or personal experience.',
      action: 'Try a short statement with a fact you want to check.',
      icon: 'message-circle', color: '#285B7D', background: '#EAF3FA',
    },
  };
  const presentation = { outcome, ...(presentations[outcome] || presentations.insufficient_evidence) };
  const forecast = result.forecast_context;
  // A partial temperature comparison must not hide a whole-claim finding
  // from an explicit source refutation or conflicting evidence.
  const showForecastHeadline = !['supported', 'contradicted', 'conflicting', 'not_checkable'].includes(outcome)
    || (outcome === 'supported' && forecast?.status === 'supported_by_forecast');
  if (forecast && showForecastHeadline) {
    const forecastMessages = {
      not_supported_by_forecast: {
        title: 'Not supported by the current forecast',
        meaning: 'The forecast we checked does not support the stated temperature. A forecast is not a guarantee of what will happen.',
      },
      supported_by_forecast: {
        title: outcome === 'supported' ? 'The reported forecast matches' : 'The forecast supports part of this claim',
        meaning: outcome === 'supported' ? 'The temperature agrees with the forecast we checked. Actual weather can still change.' : 'The temperature is consistent with the forecast, but that does not confirm every part of this message.',
      },
      mixed: { title: 'The forecasts differ', meaning: 'The forecasts we found disagree. Check the latest official update before relying on this message.' },
      unresolved: { title: 'We could not compare the full forecast', meaning: 'The available forecast does not cover all the dates, places or temperature details needed to check this message.' },
    };
    return { ...presentation, ...forecastMessages[forecast.status], action: 'Check the latest official forecast before making plans or sharing this message.' };
  }
  if (['unsupported', 'insufficient_evidence'].includes(outcome)
      && result.claim_context?.claim_type !== 'weather_forecast'
      && (result.policy_context?.change_status === 'unverified' || result.date_context?.is_future)) {
    presentation.meaning = 'The sources do not confirm this future change. This does not mean it is false.';
  }
  return presentation;
}

export function datePresentation(context) {
  if (!context?.display_date) return null;
  if (context.basis === 'relative_submission_date') return {
    title: 'The dates we checked',
    explanation: `We read "${context.claim_text}" as ${context.display_date}, using Singapore time when you submitted the message.`,
    caution: 'An older forwarded message may mean different dates. Edit the dates if needed.',
    action: 'Change the dates',
  };
  if (context.basis === 'explicit_date') return {
    title: 'The dates we checked', explanation: `We checked the dates stated in your message: ${context.display_date}.`,
    caution: 'If the message refers to different dates, edit it and check again.', action: 'Change the dates',
  };
  return { title: 'The year matters', explanation: `Your message did not include a year. We checked it as ${context.display_date}.`,
    caution: 'If that is the wrong year, change it before relying on this result.', action: 'Change the year' };
}

export function plainSourceStance(stance) {
  return { supporting: 'Supports the claim', contradicting: 'Disagrees with the claim', neutral: 'Does not settle the claim' }[stance] || 'Read this source';
}
