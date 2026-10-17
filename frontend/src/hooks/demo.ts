import { createContext, useContext } from 'react';
import type { ReviewerRole } from '../types/api';

export const DemoContext = createContext<{
  role: ReviewerRole;
  setRole: (role: ReviewerRole) => void;
}>({ role: 'Regulatory Specialist', setRole: () => undefined });
export const useDemo = () => useContext(DemoContext);
