import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { hasAWSCredentials } from "../utils/awsCredentialsHelper";

export type OnboardingStatus = "not_started" | "in_progress" | "completed";

export interface OnboardingContextType {
  onboardingStatus: OnboardingStatus;
  isOnboardingRequired: boolean;

  startOnboarding: () => void;
  completeOnboarding: () => Promise<void>;

  checkOnboardingStatus: () => Promise<void>;
  refreshOnboardingStatus: () => Promise<void>;

  skipOnboarding: () => void;
}

// IMPORTANT: utiliser null plutôt que undefined évite pas mal de soucis de typings
const OnboardingContext = createContext<OnboardingContextType | null>(null);

export function useOnboarding(): OnboardingContextType {
  const context = useContext(OnboardingContext);
  if (!context) {
    throw new Error("useOnboarding must be used within an OnboardingProvider");
  }
  return context;
}

type OnboardingProviderProps = {
  children: React.ReactNode;
};

export function OnboardingProvider({
  children,
}: OnboardingProviderProps): JSX.Element {
  const [onboardingStatus, setOnboardingStatus] =
    useState<OnboardingStatus>("not_started");
  const [isOnboardingRequired, setIsOnboardingRequired] =
    useState<boolean>(false);

  // Vérifie si l'utilisateur a déjà des credentials AWS (basé sur la DB)
  const checkOnboardingStatus = useCallback(async () => {
    try {
      const hasCredentials = await hasAWSCredentials();

      if (hasCredentials) {
        setOnboardingStatus("completed");
        setIsOnboardingRequired(false);
      } else {
        setOnboardingStatus("not_started");
        setIsOnboardingRequired(true);
      }
    } catch (error) {
      console.error("Error checking onboarding status:", error);
      // Par sécurité: si doute => onboarding requis
      setOnboardingStatus("not_started");
      setIsOnboardingRequired(true);
    }
  }, []);

  const startOnboarding = useCallback(() => {
    setOnboardingStatus("in_progress");
    setIsOnboardingRequired(true);
  }, []);

  const completeOnboarding = useCallback(async () => {
    try {
      const hasCredentials = await hasAWSCredentials();

      if (hasCredentials) {
        setOnboardingStatus("completed");
        setIsOnboardingRequired(false);
      } else {
        console.warn(
          "Onboarding completion requested but no credentials found in DB",
        );
        setOnboardingStatus("not_started");
        setIsOnboardingRequired(true);
      }
    } catch (error) {
      console.error(
        "Error verifying credentials during onboarding completion:",
        error,
      );
      setOnboardingStatus("not_started");
      setIsOnboardingRequired(true);
    }
  }, []);

  const skipOnboarding = useCallback(() => {
    // On ne “skip” pas vraiment : on garde required=true pour forcer la config AWS
    setOnboardingStatus("not_started");
    setIsOnboardingRequired(true);
  }, []);

  const refreshOnboardingStatus = useCallback(async () => {
    await checkOnboardingStatus();
  }, [checkOnboardingStatus]);

  // Vérifie au montage si l'utilisateur est connecté
  useEffect(() => {
    // IMPORTANT: tu utilises parfois "dac_access_token" ailleurs.
    // Ici, on check les deux pour éviter les incohérences.
    const token =
      localStorage.getItem("dac_access_token") ||
      localStorage.getItem("access_token");

    if (token) {
      checkOnboardingStatus();
    }
  }, [checkOnboardingStatus]);

  const contextValue: OnboardingContextType = useMemo(
    () => ({
      onboardingStatus,
      isOnboardingRequired,
      startOnboarding,
      completeOnboarding,
      checkOnboardingStatus,
      refreshOnboardingStatus,
      skipOnboarding,
    }),
    [
      onboardingStatus,
      isOnboardingRequired,
      startOnboarding,
      completeOnboarding,
      checkOnboardingStatus,
      refreshOnboardingStatus,
      skipOnboarding,
    ],
  );

  return (
    <OnboardingContext.Provider value={contextValue}>
      {children}
    </OnboardingContext.Provider>
  );
}
