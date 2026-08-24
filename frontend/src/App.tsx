// © 2024–2026 TOURE Arnaud Patrick
// Licensed under the MIT License

import {
  BrowserRouter as Router,
  Routes,
  Route,
  Navigate,
  useNavigate,
} from "react-router-dom";
import { AuthProvider, useAuth } from "./context/AuthContext";
import { ToastProvider } from "./contexts/ToastContext";
import { ChatModeProvider } from "./contexts/ChatModeContext"; //  Mode Free/DAC
import { ExecutionProvider } from "./contexts/ExecutionContext"; //  Execution tracking
import {
  OnboardingProvider,
  useOnboarding,
} from "./contexts/OnboardingContext";
import AuthModal from "./components/Auth/AuthModal";
import OnboardingWizard from "./components/Onboarding/OnboardingWizard";
import AWSOnlyWizard from "./components/Onboarding/AWSOnlyWizard";
import OnboardingGuard from "./components/Guards/OnboardingGuard";
import AppLayout from "./components/Layout/AppLayout";
import Dashboard from "./pages/Dashboard";
import Resources from "./pages/Resources";
import Chat from "./pages/Chat";
import Profile from "./pages/Profile";
import Landing from "./pages/Landing";
import OnboardingRequired from "./pages/OnboardingRequired";
import NotFound from "./pages/NotFound";
import { ErrorBoundary } from "./components/ErrorBoundary";

const AppRoutes = () => {
  const { token } = useAuth();
  const { onboardingStatus, completeOnboarding } = useOnboarding();

  const navigate = useNavigate();

  const handleOnboardingComplete = async () => {
    // Avoid duplicate network calls: OnboardingWizard already attempts to
    // mark onboarding as completed. Only call completeOnboarding if status
    // is not yet completed.
    if (onboardingStatus !== "completed") {
      await completeOnboarding();
    }

    // Ensure user is redirected to the chat after onboarding
    navigate("/chat", { replace: true });
  };

  const isOnboardingComplete = onboardingStatus === "completed";
  const showOnboardingWizard = onboardingStatus === "in_progress";

  return (
    <>
      <Routes>
        {/* Landing page publique */}
        <Route path="/" element={<Landing />} />

        {/* Routes publiques d'inscription */}
        <Route path="/register" element={<AuthModal />} />

        {!token ? (
          // Routes publiques pour utilisateurs non connectés
          <>
            <Route path="/auth" element={<AuthModal />} />
            <Route path="*" element={<Navigate to="/" />} />
          </>
        ) : (
          <>
            {/* Routes protégées avec layout d'application */}
            <Route
              path="/dashboard"
              element={
                <OnboardingGuard fallback={<OnboardingRequired />}>
                  <AppLayout>
                    <Dashboard />
                  </AppLayout>
                </OnboardingGuard>
              }
            />

            <Route path="/chat" element={<Chat />} />

            <Route path="/onboarding/aws" element={<AWSOnlyWizard />} />

            <Route
              path="/resources"
              element={
                <OnboardingGuard fallback={<OnboardingRequired />}>
                  <AppLayout>
                    <Resources />
                  </AppLayout>
                </OnboardingGuard>
              }
            />

            <Route
              path="/settings"
              element={
                <OnboardingGuard fallback={<OnboardingRequired />}>
                  <AppLayout>
                    <Profile />
                  </AppLayout>
                </OnboardingGuard>
              }
            />

            <Route
              path="/profile"
              element={
                <OnboardingGuard fallback={<OnboardingRequired />}>
                  <AppLayout>
                    <Profile />
                  </AppLayout>
                </OnboardingGuard>
              }
            />

            {/* Redirection par défaut vers dashboard */}
            <Route path="/" element={<Navigate to="/dashboard" />} />
            <Route path="*" element={<NotFound />} />
          </>
        )}
      </Routes>

      {/* Wizard d'onboarding (affiché si utilisateur connecté mais pas onboardé) */}
      {token && showOnboardingWizard && (
        <OnboardingWizard
          open={!isOnboardingComplete}
          onComplete={handleOnboardingComplete}
          allowClose={false}
        />
      )}
    </>
  );
};

const App = () => {
  return (
    <AuthProvider>
      <OnboardingProvider>
        <ChatModeProvider>
          <ExecutionProvider>
            <ToastProvider>
              <Router>
                <ErrorBoundary>
                  <AppRoutes />
                </ErrorBoundary>
              </Router>
            </ToastProvider>
          </ExecutionProvider>
        </ChatModeProvider>
      </OnboardingProvider>
    </AuthProvider>
  );
};

export default App;
