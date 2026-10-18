import { useEffect, useState } from 'react';

const STEPS = [1, 1.125, 1.25, 1.375];
const STORAGE_KEY = 'regimpact-text-scale';

function storedStep(): number {
  try {
    const index = Number(localStorage.getItem(STORAGE_KEY));
    return Number.isInteger(index) && index >= 0 && index < STEPS.length ? index : 0;
  } catch {
    return 0;
  }
}

/** Lets a reader enlarge all text; the choice is remembered in this browser only. */
export function TextSizeControl() {
  const [step, setStep] = useState(storedStep);
  useEffect(() => {
    document.documentElement.style.setProperty('--text-scale', String(STEPS[step]));
    try {
      localStorage.setItem(STORAGE_KEY, String(step));
    } catch {
      // Storage can be unavailable (private mode); the size still applies for this visit.
    }
  }, [step]);
  return (
    <div className="text-size-control" role="group" aria-label="Text size">
      <span aria-hidden="true">TEXT SIZE</span>
      <div>
        <button
          type="button"
          aria-label="Smaller text"
          disabled={step === 0}
          onClick={() => setStep((value) => Math.max(0, value - 1))}
        >
          A−
        </button>
        <button
          type="button"
          aria-label={`Reset text size (now ${Math.round(STEPS[step] * 100)}%)`}
          aria-pressed={step === 0}
          onClick={() => setStep(0)}
        >
          {Math.round(STEPS[step] * 100)}%
        </button>
        <button
          type="button"
          aria-label="Larger text"
          disabled={step === STEPS.length - 1}
          onClick={() => setStep((value) => Math.min(STEPS.length - 1, value + 1))}
        >
          A+
        </button>
      </div>
    </div>
  );
}
