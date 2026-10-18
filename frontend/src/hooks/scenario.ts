import { useQuery } from '@tanstack/react-query';
import { dashboardQuery } from '../api/queries';
import type { Scenario } from '../types/api';

const PROPOSAL_COPY = {
  sourceEyebrow: 'MAS CONSULTATION',
  scenarioEyebrow: 'ACTIVE HORIZON SCENARIO',
  changesEyebrow: 'MAS / HORIZON SCENARIO',
  changesDescription:
    'Trace each proposed change to its baseline, supporting evidence and prospective control impact.',
  baselineTitle: 'Approved baseline',
  baselineBadge: 'MAS guideline',
  changeEyebrow: 'IF ADOPTED',
  changeTitle: 'Change proposal',
  changeBadge: 'Consultation',
  cardBadge: 'Proposal',
  allChanges: 'All proposed changes',
  noBaseline: 'No equivalent baseline obligation is asserted for this proposed change.',
  interpretationNote:
    'Curated interpretation for specialist review. Proposal decisions do not alter the approved baseline.',
  newObligation: 'New proposed obligation',
  newObligations: 'New proposed obligations',
  controlsHeading: 'Controls to review if adopted',
  scopeEyebrow: 'PROPOSED SCOPE TO REVIEW',
  sourceGroup: 'Proposal source / provision',
  sourceBadge: 'Proposed',
  controlReviewIntro: 'Review which control objectives need attention if the proposal is adopted.',
};

export type ScenarioCopy = typeof PROPOSAL_COPY;

const FINAL_COPY: ScenarioCopy = {
  sourceEyebrow: 'MAS FINAL GUIDELINES',
  scenarioEyebrow: 'FINAL RULES RECEIVED',
  changesEyebrow: 'MAS / FINAL GUIDELINES',
  changesDescription:
    'Compare each obligation prepared on the draft with the final text, its evidence and the controls it affects.',
  baselineTitle: 'Prepared on the draft',
  baselineBadge: 'Consultation draft',
  changeEyebrow: 'FINAL TEXT',
  changeTitle: 'Final guideline',
  changeBadge: 'Final',
  cardBadge: 'Final',
  allChanges: 'All changes',
  noBaseline: 'New in the final text: there is no draft paragraph to compare.',
  interpretationNote:
    'Curated interpretation for specialist review. Decisions here do not alter the approved baseline.',
  newObligation: 'New final obligation',
  newObligations: 'New obligations',
  controlsHeading: 'Controls to review',
  scopeEyebrow: 'SCOPE TO REVIEW',
  sourceGroup: 'Final guideline paragraph',
  sourceBadge: 'Final',
  controlReviewIntro: 'Review which control objectives need attention under the final guidelines.',
};

/** Wording that depends on whether the active scenario is a proposal or a final instrument. */
export function useScenarioMode(): { final: boolean; scenario?: Scenario; copy: ScenarioCopy } {
  const dashboard = useQuery(dashboardQuery);
  const scenario = dashboard.data?.scenario;
  const final = scenario?.status === 'FINAL';
  return { final, scenario, copy: final ? FINAL_COPY : PROPOSAL_COPY };
}
