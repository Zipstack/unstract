import { isChunkLoadError, reloadOnce } from "@v1/lib/chunkReload";
import { Component, type ReactNode } from "react";

type BoundaryState = { failed: boolean };

function sessionStore(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

/**
 * Keeps a v1 failure from unmounting the whole app. A stale chunk after a
 * deploy reloads the page once to fetch the new one (React caches a failed
 * lazy import, so nothing short of a reload retries it); anything else, or a
 * repeat failure, shows the fallback. Navigating to another URL clears it, as
 * v0's backstop does with `resetKeys`. RouteGate also wraps each page in one,
 * so a page error stays the page's, not a gate plugin's.
 */
export class V1ErrorBoundary extends Component<
  { children: ReactNode; resetKey: string },
  BoundaryState
> {
  override state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  override componentDidUpdate(prev: Readonly<{ resetKey: string }>): void {
    if (this.state.failed && prev.resetKey !== this.props.resetKey) {
      this.setState({ failed: false });
    }
  }

  override componentDidCatch(error: unknown): void {
    if (isChunkLoadError(error)) {
      reloadOnce(sessionStore(), () => window.location.reload());
    }
  }

  override render(): ReactNode {
    if (this.state.failed) {
      return (
        <div className="ui:p-6" role="alert">
          <p>This page could not be loaded.</p>
          <button type="button" onClick={() => window.location.reload()}>
            Reload
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
