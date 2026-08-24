import {
  Dialog,
  DialogContent,
  Box,
  Stepper,
  Step,
  StepLabel,
  alpha,
  Slide,
  IconButton,
  Tooltip,
} from "@mui/material";
import { Close } from "@mui/icons-material";
import { forwardRef, useState, useEffect } from "react";
import {
  OnboardingStep,
  ONBOARDING_STEP_LABELS,
} from "../../utils/onboardingUtils";
import type { AWSCredentials } from "../../utils/awsValidator";
import { saveAndValidateAWSCredentials } from "../../utils/awsValidator";
import { useOnboarding } from "../../contexts/OnboardingContext";
import { useToast } from "../../contexts/ToastContext";

import OnboardingWelcome from "./OnboardingWelcome";
import AWSCredentialsSetup from "./AWSCredentialsSetup";
import AWSCredentialsValidator from "./AWSCredentialsValidator";
import OnboardingSuccess from "./OnboardingSuccess";

const STORAGE_KEY = "onboarding_current_step";

const Transition = forwardRef(function Transition(props: any, ref: any) {
  return <Slide direction="up" ref={ref} {...props} />;
});

interface OnboardingWizardProps {
  open: boolean;
  onComplete: () => void;
  allowClose?: boolean;
}

export default function OnboardingWizard({
  open,
  onComplete,
  allowClose = false,
}: OnboardingWizardProps) {
  // Restaurer l'étape depuis localStorage au montage
  const getInitialStep = () => {
    try {
      const savedStep = localStorage.getItem(STORAGE_KEY);
      if (savedStep) {
        const step = parseInt(savedStep, 10);
        if (step >= OnboardingStep.WELCOME && step <= OnboardingStep.SUCCESS) {
          return step;
        }
      }
    } catch (error) {
      console.error("Error reading onboarding step from localStorage:", error);
    }
    return OnboardingStep.WELCOME;
  };

  const [currentStep, setCurrentStep] = useState(getInitialStep);
  const [credentials, setCredentials] = useState<AWSCredentials | null>(null);
  const [isValidating, setIsValidating] = useState(false);

  const { completeOnboarding } = useOnboarding();
  const { showError } = useToast();

  // Sauvegarder l'étape dans localStorage à chaque changement
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, currentStep.toString());
    } catch (error) {
      console.error("Error saving onboarding step to localStorage:", error);
    }
  }, [currentStep]);

  const handleNext = () => {
    if (currentStep < OnboardingStep.SUCCESS) {
      setCurrentStep(currentStep + 1);
    }
  };

  const handleBack = () => {
    if (currentStep > OnboardingStep.WELCOME) {
      setCurrentStep(currentStep - 1);
    }
  };

  const handleCredentialsSubmit = async (creds: AWSCredentials) => {
    setCredentials(creds);
    setIsValidating(true);

    try {
      const result = await saveAndValidateAWSCredentials(creds);

      if (result.isValid) {
        setCurrentStep(OnboardingStep.VALIDATION);
      } else {
        showError(
          result.error || "Erreur lors de la validation des credentials",
        );
      }
    } catch (error) {
      showError("Erreur lors de la sauvegarde des credentials");
    } finally {
      setIsValidating(false);
    }
  };

  const handleValidationNext = () => {
    setCurrentStep(OnboardingStep.SUCCESS);
  };

  const handleRetryCredentials = () => {
    setCurrentStep(OnboardingStep.AWS_SETUP);
  };

  const handleComplete = async () => {
    await completeOnboarding();
    // Nettoyer le localStorage une fois l'onboarding terminé
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      console.error("Error clearing onboarding step from localStorage:", error);
    }
    onComplete();
  };

  const handleClose = () => {
    if (allowClose) {
      onComplete();
    }
  };

  const steps = [
    ONBOARDING_STEP_LABELS[OnboardingStep.WELCOME],
    ONBOARDING_STEP_LABELS[OnboardingStep.AWS_SETUP],
    ONBOARDING_STEP_LABELS[OnboardingStep.VALIDATION],
    ONBOARDING_STEP_LABELS[OnboardingStep.SUCCESS],
  ];

  return (
    <Dialog
      open={open}
      TransitionComponent={Transition}
      fullScreen
      PaperProps={{
        sx: {
          bgcolor: "background.default",
          backgroundImage: "linear-gradient(180deg, #0f172a 0%, #1e293b 100%)",
        },
      }}
      BackdropProps={{
        sx: {
          bgcolor: alpha("#0f172a", 0.9),
          backdropFilter: "blur(8px)",
        },
      }}
    >
      {/* Close Button (only if allowed) */}
      {allowClose && (
        <Box
          sx={{
            position: "absolute",
            top: 16,
            right: 16,
            zIndex: 1000,
          }}
        >
          <Tooltip title="Fermer">
            <IconButton
              onClick={handleClose}
              sx={{
                bgcolor: alpha("#1e293b", 0.8),
                backdropFilter: "blur(20px)",
                border: "1px solid",
                borderColor: alpha("#475569", 0.3),
                color: "text.secondary",
                "&:hover": {
                  bgcolor: alpha("#374151", 0.8),
                  color: "text.primary",
                },
              }}
            >
              <Close />
            </IconButton>
          </Tooltip>
        </Box>
      )}

      <DialogContent sx={{ p: 0, overflow: "hidden" }}>
        <Box
          sx={{
            minHeight: "100vh",
            maxHeight: "100vh",
            display: "flex",
            flexDirection: "column",
            overflowY: "auto",
          }}
        >
          {/* Progress Stepper */}
          <Box
            sx={{
              py: 4,
              px: 2,
              borderBottom: "1px solid",
              borderColor: alpha("#475569", 0.3),
              bgcolor: alpha("#1e293b", 0.5),
              backdropFilter: "blur(20px)",
            }}
          >
            <Stepper
              activeStep={currentStep}
              alternativeLabel
              sx={{
                maxWidth: 600,
                mx: "auto",
                "& .MuiStepLabel-label": {
                  color: "text.secondary",
                  fontSize: "0.875rem",
                  "&.Mui-active": {
                    color: "primary.main",
                    fontWeight: 600,
                  },
                  "&.Mui-completed": {
                    color: "success.main",
                    fontWeight: 500,
                  },
                },
                "& .MuiStepIcon-root": {
                  color: alpha("#475569", 0.5),
                  "&.Mui-active": {
                    color: "primary.main",
                  },
                  "&.Mui-completed": {
                    color: "success.main",
                  },
                },
              }}
            >
              {steps.map((label) => (
                <Step key={label}>
                  <StepLabel>{label}</StepLabel>
                </Step>
              ))}
            </Stepper>
          </Box>

          {/* Step Content */}
          <Box
            sx={{
              flex: 1,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              py: 4,
              px: 2,
              overflow: "auto",
            }}
          >
            {currentStep === OnboardingStep.WELCOME && (
              <OnboardingWelcome onNext={handleNext} />
            )}

            {currentStep === OnboardingStep.AWS_SETUP && (
              <AWSCredentialsSetup
                onNext={handleCredentialsSubmit}
                onBack={handleBack}
                loading={isValidating}
              />
            )}

            {currentStep === OnboardingStep.VALIDATION && credentials && (
              <AWSCredentialsValidator
                credentials={credentials}
                onNext={handleValidationNext}
                onBack={handleBack}
                onRetry={handleRetryCredentials}
              />
            )}

            {currentStep === OnboardingStep.SUCCESS && (
              <OnboardingSuccess onComplete={handleComplete} />
            )}
          </Box>
        </Box>
      </DialogContent>
    </Dialog>
  );
}
