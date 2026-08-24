import { hasAWSCredentials } from './awsCredentialsHelper';

export enum OnboardingStep {
  WELCOME = 0,
  AWS_SETUP = 1,
  VALIDATION = 2,
  SUCCESS = 3,
}

export const ONBOARDING_STEP_LABELS = {
  [OnboardingStep.WELCOME]: 'Bienvenue',
  [OnboardingStep.AWS_SETUP]: 'Configuration AWS',
  [OnboardingStep.VALIDATION]: 'Validation',
  [OnboardingStep.SUCCESS]: 'Terminé',
};

export const ONBOARDING_STEP_DESCRIPTIONS = {
  [OnboardingStep.WELCOME]: 'Introduction à la plateforme',
  [OnboardingStep.AWS_SETUP]: 'Saisie des credentials AWS',
  [OnboardingStep.VALIDATION]: 'Test de connexion',
  [OnboardingStep.SUCCESS]: 'Configuration terminée',
};

/**
 * Vérifie si l'utilisateur peut accéder au chat
 */
export async function canAccessChat(): Promise<boolean> {
  try {
    return await hasAWSCredentials();
  } catch {
    return false;
  }
}

/**
 * Détermine si l'onboarding est requis pour un nouvel utilisateur
 */
export async function isOnboardingRequired(): Promise<boolean> {
  const hasCredentials = await hasAWSCredentials();
  const onboardingStatus = localStorage.getItem('onboarding_status');
  
  return !hasCredentials && onboardingStatus !== 'completed';
}

/**
 * Marque l'onboarding comme démarré
 */
export function markOnboardingStarted(): void {
  localStorage.setItem('onboarding_status', 'in_progress');
  localStorage.setItem('onboarding_started_at', new Date().toISOString());
}

/**
 * Marque l'onboarding comme terminé
 */
export function markOnboardingCompleted(): void {
  localStorage.setItem('onboarding_status', 'completed');
  localStorage.setItem('onboarding_completed_at', new Date().toISOString());
}

/**
 * Obtient les statistiques d'onboarding
 */
export function getOnboardingStats() {
  const status = localStorage.getItem('onboarding_status');
  const startedAt = localStorage.getItem('onboarding_started_at');
  const completedAt = localStorage.getItem('onboarding_completed_at');
  
  return {
    status,
    startedAt: startedAt ? new Date(startedAt) : null,
    completedAt: completedAt ? new Date(completedAt) : null,
    duration: startedAt && completedAt 
      ? new Date(completedAt).getTime() - new Date(startedAt).getTime()
      : null,
  };
}

/**
 * Réinitialise l'onboarding
 */
export function resetOnboarding(): void {
  localStorage.removeItem('onboarding_status');
  localStorage.removeItem('onboarding_started_at');
  localStorage.removeItem('onboarding_completed_at');
}