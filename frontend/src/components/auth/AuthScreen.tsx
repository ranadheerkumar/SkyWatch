"use client";

import type { FormEvent } from "react";
import TractorSupplyLogo from "../navigation/TractorSupplyLogo";

type AuthMode = "login" | "register";

type AuthScreenProps = {
  brandTitle: string;
  brandSubtitle: string;
  mode: AuthMode;
  email: string;
  password: string;
  error: string;
  authenticating: boolean;
  onModeChange: (mode: AuthMode) => void;
  onEmailChange: (email: string) => void;
  onPasswordChange: (password: string) => void;
  onSubmit: (event: FormEvent<HTMLFormElement>) => void;
};

export default function AuthScreen({
  brandTitle,
  brandSubtitle,
  mode,
  email,
  password,
  error,
  authenticating,
  onModeChange,
  onEmailChange,
  onPasswordChange,
  onSubmit,
}: AuthScreenProps) {
  const isLogin = mode === "login";
  return (
    <main className="auth-screen">
      <form className="auth-card" onSubmit={onSubmit}>
        <div className="brand auth-brand">
          <TractorSupplyLogo variant="auth" title={brandTitle} subtitle={brandSubtitle} />
        </div>
        <h1>{isLogin ? "Welcome back" : "Create your account"}</h1>
        <label className="capture-label">
          Email
          <input type="email" required value={email} onChange={(event) => onEmailChange(event.target.value)} placeholder="you@company.com" disabled={authenticating} />
        </label>
        <label className="capture-label">
          Password
          <input type="password" required minLength={12} value={password} onChange={(event) => onPasswordChange(event.target.value)} placeholder="At least 12 characters" disabled={authenticating} />
        </label>
        {error && <p className="form-error" role="alert">{error}</p>}
          <button type="submit" className="primary auth-submit" disabled={authenticating}>{authenticating ? "Please wait..." : isLogin ? "Sign in" : "Create account"}</button>
        <button type="button" className="auth-switch" disabled={authenticating} onClick={() => onModeChange(isLogin ? "register" : "login")}>
          {isLogin ? "Need an account? Create one" : "Already have an account? Sign in"}
        </button>
      </form>
    </main>
  );
}
