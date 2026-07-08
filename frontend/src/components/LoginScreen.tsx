import { useEffect, useState } from 'react'
import { api, ApiError } from '../api'
import type { User } from '../types'

// The auth gate: shown by App whenever there's no logged-in user. Handles both
// logging in and (when the server has signup enabled) creating an account with
// a shared invite code.
export function LoginScreen({ onAuthed }: { onAuthed: (user: User) => void }) {
  const [mode, setMode] = useState<'login' | 'signup'>('login')
  const [signupEnabled, setSignupEnabled] = useState(false)
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [inviteCode, setInviteCode] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  // Only offer the signup tab if the server has an invite code configured.
  useEffect(() => {
    api
      .authConfig()
      .then((c) => setSignupEnabled(c.signup_enabled))
      .catch(() => setSignupEnabled(false))
  }, [])

  const submit = async (event: React.FormEvent) => {
    event.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const user =
        mode === 'signup'
          ? await api.signup(username.trim(), password, inviteCode.trim())
          : await api.login(username.trim(), password)
      onAuthed(user)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : String(err))
      setSubmitting(false)
    }
  }

  const switchMode = (next: 'login' | 'signup') => {
    setMode(next)
    setError(null)
  }

  return (
    <div className="auth-screen">
      <form className="auth-card" onSubmit={submit}>
        <h1>
          Retirement Simulator
          <small>Monte Carlo plan analysis</small>
        </h1>

        {signupEnabled && (
          <div className="auth-tabs">
            <button
              type="button"
              className={mode === 'login' ? 'active' : ''}
              onClick={() => switchMode('login')}
            >
              Log in
            </button>
            <button
              type="button"
              className={mode === 'signup' ? 'active' : ''}
              onClick={() => switchMode('signup')}
            >
              Sign up
            </button>
          </div>
        )}

        <label className="auth-field">
          <span>Username</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            autoFocus
            required
          />
        </label>

        <label className="auth-field">
          <span>Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            required
          />
        </label>

        {mode === 'signup' && (
          <label className="auth-field">
            <span>Invite code</span>
            <input
              value={inviteCode}
              onChange={(e) => setInviteCode(e.target.value)}
              required
            />
          </label>
        )}

        {error && <div className="banner error">{error}</div>}

        <button className="primary" type="submit" disabled={submitting}>
          {submitting
            ? mode === 'signup'
              ? 'Creating account…'
              : 'Logging in…'
            : mode === 'signup'
              ? 'Create account'
              : 'Log in'}
        </button>
      </form>
    </div>
  )
}
