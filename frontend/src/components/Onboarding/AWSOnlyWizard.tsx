import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import OnboardingWizard from "./OnboardingWizard";
import { useOnboarding } from "../../contexts/OnboardingContext";

/**
 * AWSOnlyWizard: Wrapper pour afficher le wizard directement à l'étape AWS
 * Utilisé quand l'utilisateur clique sur "Configurer AWS" depuis la landing
 */
export default function AWSOnlyWizard() {
  const { completeOnboarding } = useOnboarding();
  const navigate = useNavigate();

  const handleComplete = async () => {
    // Mark completion then navigate to chat
    await completeOnboarding();
    navigate("/chat", { replace: true });
  };

  // Set localStorage pour démarrer à l'étape AWS (étape 1 numeric)
  useEffect(() => {
    try {
      localStorage.setItem("onboarding_current_step", "1");
    } catch (e) {
      console.error("Could not set onboarding step:", e);
    }
  }, []);

  return (
    <OnboardingWizard
      open={true}
      onComplete={handleComplete}
      allowClose={true}
    />
  );
}
