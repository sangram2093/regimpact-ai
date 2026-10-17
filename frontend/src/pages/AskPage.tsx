import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, CornerDownLeft, MessageSquareText, ShieldCheck } from 'lucide-react';
import { dashboardQuery } from '../api/queries';
import { askConfigQuery, useAsk } from '../api/workflows';
import type { AskConfig } from '../types/workflows';
import {
  Badge,
  ErrorState,
  LoadingState,
  PageHeading,
  ProposalBanner,
} from '../components/Primitives';
import { AskAnswer } from '../features/ask/AskAnswer';

function AskWorkspace({ config, scenarioId }: { config: AskConfig; scenarioId: string }) {
  const [question, setQuestion] = useState(config.suggested_questions[0] ?? '');
  const ask = useAsk();
  function submit() {
    if (config.available && question.trim().length >= 5 && !ask.isPending)
      ask.mutate({ question: question.trim(), scenario_id: scenarioId });
  }
  return (
    <>
      <div className="ask-mode-strip">
        <MessageSquareText size={17} />
        <span>{config.label}</span>
        <Badge tone={config.mode === 'gcp' || config.mode === 'LIVE_AI' ? 'teal' : 'neutral'}>
          {config.mode === 'gcp' || config.mode === 'LIVE_AI'
            ? 'Live AI configured'
            : 'Local deterministic'}
        </Badge>
      </div>
      <section className="panel ask-composer">
        <label htmlFor="ask-question">
          <span className="eyebrow">ASK ABOUT YOUR APPROVED GRAPH</span>
          <h2>Follow the evidence.</h2>
        </label>
        <textarea
          id="ask-question"
          aria-label="Question for RegImpact"
          rows={3}
          maxLength={1000}
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          onKeyDown={(event) => {
            if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
              event.preventDefault();
              submit();
            }
          }}
        />
        <div className="ask-composer-footer">
          <span>
            <ShieldCheck size={14} />
            Read-only tools · No approval or write access
          </span>
          <button
            className="button button-primary"
            disabled={!config.available || question.trim().length < 5 || ask.isPending}
            onClick={submit}
          >
            <CornerDownLeft size={15} />
            {ask.isPending ? 'Checking graph evidence…' : 'Ask RegImpact'}
          </button>
        </div>
        {!config.available && (
          <p className="role-warning">
            {config.reason ?? 'The answer workflow is not configured.'}
          </p>
        )}
      </section>
      <div className="question-suggestions" aria-label="Suggested questions">
        {config.suggested_questions.map((suggestion) => (
          <button key={suggestion} onClick={() => setQuestion(suggestion)} disabled={ask.isPending}>
            {suggestion}
            <ArrowUpRight size={14} />
          </button>
        ))}
      </div>
      {ask.isPending && (
        <LoadingState label="Reading approved graph tools and checking every reference…" />
      )}
      {ask.error && <ErrorState error={ask.error} />}
      {ask.data && !ask.isPending && <AskAnswer result={ask.data} />}
    </>
  );
}

export function AskPage() {
  const config = useQuery(askConfigQuery);
  const dashboard = useQuery(dashboardQuery);
  return (
    <>
      <PageHeading
        eyebrow="GROUNDED / READ-ONLY EXPLORATION"
        title="Ask RegImpact"
        description="Understand an impact, inspect a relationship or find a coverage gap. Every complete answer must trace back to this run’s retrieved evidence."
      />
      <ProposalBanner />
      {config.error || dashboard.error ? (
        <ErrorState
          error={config.error ?? dashboard.error!}
          retry={() => {
            void config.refetch();
            void dashboard.refetch();
          }}
        />
      ) : config.isPending || dashboard.isPending ? (
        <LoadingState />
      ) : (
        <AskWorkspace config={config.data} scenarioId={dashboard.data.scenario.id} />
      )}
    </>
  );
}
