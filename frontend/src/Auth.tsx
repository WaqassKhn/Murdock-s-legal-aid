import { useState } from 'react';
import type { FormEvent } from 'react';
import { ArrowRight, Check, Layers3, Scale, ShieldCheck } from 'lucide-react';
import { api, errorMessage, json, temporarySession } from './api';
import { Disclaimer, ErrorNotice } from './components';
import type { User } from './types';

export function Auth({ onAuthenticated }: { onAuthenticated: (user: User) => void }) {
  const [register, setRegister] = useState(true),
    [email, setEmail] = useState(''),
    [password, setPassword] = useState(''),
    [error, setError] = useState(''),
    [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      onAuthenticated(
        await api<User>(register ? '/auth/register' : '/auth/login', {
          method: 'POST',
          body: json({ email, password }),
        }),
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-layout">
      <section className="auth-story">
        <div className="brand">
          <span className="brand-icon">
            <Scale size={24} />
          </span>
          LegalLens<span className="brand-dot">.</span>
        </div>
        <div className="story-content">
          <div className="eyebrow light">
            <span className="tiny-line" />
            CLARITY, GROUNDED IN EVIDENCE
          </div>
          <h1>
            Understand the terms.
            <br />
            <em>Know what to ask.</em>
          </h1>
          <p>
            A considered space to read between the lines, connect every insight to its source, and
            prepare for your next conversation.
          </p>
          <div className="story-points">
            <span>
              <Check size={17} />
              Plain-language document analysis
            </span>
            <span>
              <Check size={17} />
              Every important claim traced to evidence
            </span>
            <span>
              <Check size={17} />A clearer conversation with your lawyer
            </span>
          </div>
          <div className="story-evidence">
            <div className="eyebrow">
              <Layers3 size={16} /> THE EVIDENCE PRINCIPLE
            </div>
            <blockquote>
              From a question to a clause.
              <br />
              From a clause to the exact page.
            </blockquote>
            <span>Document facts · Interpretation · Next steps</span>
          </div>
        </div>
        <div className="auth-foot">
          <ShieldCheck size={16} />
          Your documents. Your private workspace.
        </div>
      </section>
      <section className="auth-form-panel">
        <div className="auth-form-inner">
          {temporarySession && (
            <p role="status">
              Temporary hackathon demo. Use one tab. Create a session account using an example email
              and a throwaway password. Nothing is saved across refreshes or tab closure; export
              results before leaving. Live AI requires the deployment owner’s provider quota.
              Without it, results are labeled local extraction.
            </p>
          )}
          <div className="eyebrow">YOUR REVIEW STARTS HERE</div>
          <h2>{register ? 'A little clarity goes a long way.' : 'Welcome back.'}</h2>
          <p className="muted">
            {register
              ? 'Create a private workspace for the documents that matter.'
              : 'Continue where you left off.'}
          </p>
          <form onSubmit={submit}>
            {error && <ErrorNotice message={error} />}
            <label>
              Email address
              <input
                type="email"
                name="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
              />
            </label>
            <label>
              Password
              <input
                name="password"
                type="password"
                autoComplete={register ? 'new-password' : 'current-password'}
                minLength={12}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 12 characters"
              />
            </label>
            {register && (
              <p className="field-hint">
                Use at least 12 characters. Document analysis is informational and may need
                professional review.
              </p>
            )}
            <button className="primary full" disabled={busy}>
              {busy ? 'Please wait…' : register ? 'Create your account' : 'Sign in'}
              <ArrowRight size={17} />
            </button>
          </form>
          <p className="auth-switch">
            {register ? 'Already have an account?' : 'New to LegalLens?'}{' '}
            <button
              className="text-button"
              onClick={() => {
                setRegister(!register);
                setError('');
              }}
            >
              {register ? 'Sign in' : 'Create an account'}
            </button>
          </p>
          <Disclaimer />
        </div>
      </section>
    </main>
  );
}
