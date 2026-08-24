import type { ReactNode } from 'react';
import { useOnboarding } from '../../contexts/OnboardingContext';

interface OnboardingGuardProps {
  children: ReactNode;
  fallback?: ReactNode;
}

export default function OnboardingGuard({ children, fallback }: OnboardingGuardProps) {
  const { onboardingStatus } = useOnboarding();
  
  const isOnboardingComplete = onboardingStatus === 'completed';

  if (!isOnboardingComplete) {
    return fallback || null;
  }

  return <>{children}</>;
}