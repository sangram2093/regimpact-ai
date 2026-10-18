import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderApp } from './render';
import { dashboard } from './fixtures';

const success = (data: unknown) =>
  new Response(JSON.stringify({ data, meta: { request_id: 'role-strip-test' } }), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

describe('Demo reviewer role', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (input: string) =>
        input.endsWith('/dashboard')
          ? success(dashboard)
          : new Response(JSON.stringify({ error: { code: 'NOT_FOUND', message: 'Not in test' } }), {
              status: 404,
              headers: { 'Content-Type': 'application/json' },
            }),
      ),
    );
  });

  it('shows the active role and what it may decide on every page', async () => {
    const user = userEvent.setup();
    renderApp('/dashboard');
    expect(await screen.findByText(/confirm change effects/)).toBeInTheDocument();
    expect(screen.getByTitle('Acting as Regulatory Specialist')).toHaveTextContent('RS');

    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Policy Owner');
    expect(screen.getByText(/authorize control impact/)).toBeInTheDocument();
    expect(screen.getByTitle('Acting as Policy Owner')).toHaveTextContent('PO');

    await user.selectOptions(screen.getByLabelText('DEMO REVIEWER ROLE'), 'Risk Steward');
    expect(screen.getByText(/risk-classification runs/)).toBeInTheDocument();
    expect(screen.getByTitle('Acting as Risk Steward')).toHaveTextContent('RK');
  });
});
