import React from "react";

type Props = { children: React.ReactNode };
type State = { hasError: boolean; message?: string };

export class ErrorBoundary extends React.Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(err: unknown) {
    return {
      hasError: true,
      message: err instanceof Error ? err.message : String(err),
    };
  }

  componentDidCatch(error: unknown, info: unknown) {
    console.error("UI crashed:", error, info);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: 16 }}>
          <h3>Erreur UI</h3>
          <pre style={{ whiteSpace: "pre-wrap" }}>{this.state.message}</pre>
          <button onClick={() => window.location.reload()}>Recharger</button>
        </div>
      );
    }
    return this.props.children;
  }
}
