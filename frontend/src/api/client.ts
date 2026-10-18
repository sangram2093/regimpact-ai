import type { Envelope } from '../types/api';

const SESSION_KEY = 'regimpact-demo-session';
const SCENARIO_KEY = 'regimpact-scenario';
export const DEFAULT_SCENARIO = 'mas-2023';

export function scenarioKey(): string {
  try {
    return sessionStorage.getItem(SCENARIO_KEY) || DEFAULT_SCENARIO;
  } catch {
    return DEFAULT_SCENARIO;
  }
}

export function setScenarioKey(key: string): void {
  try {
    sessionStorage.setItem(SCENARIO_KEY, key);
  } catch {
    // Without storage the default scenario remains selected.
  }
}

export function sessionId(): string {
  let id = sessionStorage.getItem(SESSION_KEY);
  if (!id) {
    id = crypto.randomUUID();
    sessionStorage.setItem(SESSION_KEY, id);
  }
  return id;
}

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly requestId?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function request<T>(path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`/api/v1${path}`, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Demo-Session': sessionId(),
        'X-RegImpact-Scenario': scenarioKey(),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  } catch {
    throw new ApiError('The local API is unreachable. Start the backend and try again.', 'NETWORK');
  }
  let result: Envelope<T> & {
    error?: { code: string; message: string };
  };
  try {
    result = await response.json();
  } catch {
    throw new ApiError(
      'The API returned an unreadable response. Check the backend connection.',
      'INVALID_RESPONSE',
    );
  }
  if (!response.ok || result.error) {
    throw new ApiError(
      result.error?.message ?? 'This action could not be completed. Please try again.',
      result.error?.code ?? 'REQUEST_FAILED',
      result.meta?.request_id,
    );
  }
  return result.data;
}
