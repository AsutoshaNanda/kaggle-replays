// Public landing page — marketing entry for global/public users.
// Hero, feature grid, "how it works", footer. CTA routes to /login.

import type { ComponentType, JSX } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ArrowUpRightIcon,
  BoltIcon,
  DownloadIcon,
  GlobeIcon,
  LockIcon,
  PackageIcon,
  SparkleIcon,
  TargetIcon,
} from '@/components/shared/icons'

const fadeUp = {
  hidden: { opacity: 0, y: 24 },
  show: { opacity: 1, y: 0, transition: { duration: 0.55, ease: 'easeOut' } },
} as const

export function LandingPage(): JSX.Element {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-base)' }}>
      <LandingNav />
      <Hero />
      <Features />
      <HowItWorks />
      <CTA />
      <Footer />
    </div>
  )
}

function LandingNav(): JSX.Element {
  return (
    <header
      style={{
        position: 'sticky',
        top: 0,
        zIndex: 50,
        backdropFilter: 'blur(12px)',
        background: 'rgba(250,248,243,0.72)',
        borderBottom: '1px solid var(--border-subtle)',
      }}
    >
      <div
        className="mx-auto flex items-center justify-between px-4 md:px-8"
        style={{ maxWidth: 1200, height: 64 }}
      >
        <Link
          to="/"
          className="flex items-center gap-2"
          style={{ fontFamily: 'var(--font-mono)', fontSize: '1rem', color: 'var(--text-primary)' }}
        >
          <span aria-hidden="true" style={{ color: 'var(--accent-cyan)', display: 'inline-flex' }}><BoltIcon size={22} /></span>
          <span style={{ letterSpacing: '0.02em' }}>replay.analytics</span>
        </Link>
        <nav className="hidden md:flex items-center gap-8" aria-label="Primary">
          <a href="#features" style={{ color: 'var(--text-muted)', fontSize: '0.92rem' }}>Features</a>
          <a href="#how" style={{ color: 'var(--text-muted)', fontSize: '0.92rem' }}>How it works</a>
          <a
            href="https://www.kaggle.com/competitions"
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1"
            style={{ color: 'var(--text-muted)', fontSize: '0.92rem' }}
          >
            Kaggle
            <ArrowUpRightIcon size={14} />
          </a>
        </nav>
        <Link to="/login" className="btn-primary-glow" style={{ padding: '8px 18px', fontSize: '0.9rem' }}>
          Sign in
        </Link>
      </div>
    </header>
  )
}

function Hero(): JSX.Element {
  return (
    <section
      className="mesh-bg-animated relative"
      style={{ overflow: 'hidden', borderBottom: '1px solid var(--border-subtle)' }}
    >
      <svg
        aria-hidden="true"
        style={{
          position: 'absolute', inset: 0, width: '100%', height: '100%',
          opacity: 0.04, pointerEvents: 'none', mixBlendMode: 'overlay',
        }}
      >
        <filter id="landing-noise">
          <feTurbulence type="fractalNoise" baseFrequency="0.85" numOctaves="2" stitchTiles="stitch" />
          <feColorMatrix type="saturate" values="0" />
        </filter>
        <rect width="100%" height="100%" filter="url(#landing-noise)" />
      </svg>

      <div
        className="relative mx-auto px-4 md:px-8 text-center"
        style={{ maxWidth: 980, paddingTop: 'clamp(80px, 14vw, 160px)', paddingBottom: 'clamp(80px, 14vw, 160px)' }}
      >
        <motion.div initial="hidden" animate="show" variants={fadeUp}>
          <div
            className="pill pill-info mx-auto mb-6"
            style={{ width: 'fit-content' }}
          >
            <span aria-hidden="true" style={{ display: 'inline-flex' }}><SparkleIcon size={13} /></span>
            <span>For Kaggle competitors, worldwide</span>
          </div>
        </motion.div>

        <motion.h1
          initial="hidden"
          animate="show"
          variants={fadeUp}
          transition={{ delay: 0.08 }}
          style={{
            fontFamily: 'var(--font-display)',
            fontSize: 'clamp(2.75rem, 7vw, 5.5rem)',
            lineHeight: 1.02,
            letterSpacing: '-0.035em',
            fontWeight: 700,
            marginBottom: 24,
          }}
        >
          Turn competition replays
          <br />
          into <span className="gradient-text">winning insight</span>.
        </motion.h1>

        <motion.p
          initial="hidden"
          animate="show"
          variants={fadeUp}
          transition={{ delay: 0.16 }}
          className="mx-auto"
          style={{
            color: 'var(--text-primary)',
            opacity: 0.78,
            fontSize: 'clamp(1.05rem, 1.6vw, 1.25rem)',
            maxWidth: 680,
            marginBottom: 40,
            lineHeight: 1.55,
          }}
        >
          Bulk-download submission replays from any Kaggle simulation competition,
          filter by score and outcome, and study the games that matter — all from
          one fast, keyboard-friendly workspace.
        </motion.p>

        <motion.div
          initial="hidden"
          animate="show"
          variants={fadeUp}
          transition={{ delay: 0.24 }}
          className="flex flex-wrap items-center justify-center gap-3"
        >
          <Link to="/login" className="btn-primary-glow btn-lg">
            Get started — it&apos;s free
          </Link>
          <a href="#features" className="btn-ghost">
            See features
          </a>
        </motion.div>

        <motion.div
          initial="hidden"
          animate="show"
          variants={fadeUp}
          transition={{ delay: 0.34 }}
          className="mx-auto mt-16"
          style={{ maxWidth: 880 }}
        >
          <div
            className="glass-card"
            style={{ padding: 0, overflow: 'hidden', boxShadow: 'var(--shadow-lg)' }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                padding: '12px 16px',
                borderBottom: '1px solid var(--border-subtle)',
                background: 'var(--bg-surface)',
              }}
            >
              <span style={{ width: 10, height: 10, borderRadius: 999, background: 'var(--accent-red)' }} />
              <span style={{ width: 10, height: 10, borderRadius: 999, background: 'var(--accent-amber)' }} />
              <span style={{ width: 10, height: 10, borderRadius: 999, background: 'var(--accent-green)' }} />
              <span
                className="mono"
                style={{ marginLeft: 12, color: 'var(--text-faint)', fontSize: '0.75rem' }}
              >
                replay.analytics / competitions
              </span>
            </div>
            <div style={{ padding: 24, display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 16 }}>
              {[
                { title: 'Lux AI S3', meta: '2,481 teams', score: 1843, tone: 'high' },
                { title: 'Halite IV', meta: '1,124 teams', score: 1042, tone: 'mid' },
                { title: 'ConnectX', meta: '893 teams', score: 612, tone: 'low' },
              ].map((c) => (
                <div key={c.title} className="glass-card" style={{ padding: 14 }}>
                  <div className="gradient-line" style={{ marginBottom: 12 }} />
                  <div style={{ fontFamily: 'var(--font-display)', fontWeight: 600, marginBottom: 4 }}>
                    {c.title}
                  </div>
                  <div style={{ color: 'var(--text-muted)', fontSize: '0.78rem', marginBottom: 10 }}>
                    {c.meta}
                  </div>
                  <span className={`score-badge score-badge-${c.tone}`}>{c.score}</span>
                </div>
              ))}
            </div>
          </div>
        </motion.div>
      </div>
    </section>
  )
}

const FEATURES: { Icon: ComponentType<{ size?: number }>; title: string; body: string }[] = [
  {
    Icon: DownloadIcon,
    title: 'Bulk replay download',
    body: 'Pull thousands of submission replays in parallel with live progress, retry, and per-episode filtering.',
  },
  {
    Icon: TargetIcon,
    title: 'Score-aware filtering',
    body: 'Slice submissions by score thresholds, outcome (win / draw / loss), and episode count — find the games worth studying.',
  },
  {
    Icon: BoltIcon,
    title: 'Fast, keyboard-first UI',
    body: 'Built for power users. Switch competitions, sort tables, and queue downloads without leaving the keyboard.',
  },
  {
    Icon: PackageIcon,
    title: 'JSON or HTML formats',
    body: 'Export replays in the format your analysis pipeline expects — raw JSON for ML, rendered HTML for review.',
  },
  {
    Icon: LockIcon,
    title: 'Your Kaggle, your data',
    body: 'Authenticate with your own Kaggle account. We never store passwords and you keep ownership of every download.',
  },
  {
    Icon: GlobeIcon,
    title: 'Works anywhere',
    body: 'A modern web app that runs in any browser, on any continent — no install, no native dependencies.',
  },
]

function Features(): JSX.Element {
  return (
    <section id="features" style={{ padding: 'clamp(80px, 12vw, 140px) 0' }}>
      <div className="mx-auto px-4 md:px-8" style={{ maxWidth: 1200 }}>
        <SectionHeader
          eyebrow="What it does"
          title={<>Every replay, <span className="gradient-text">organized</span>.</>}
          subtitle="A focused toolkit for serious Kaggle competitors. No clutter, no fluff."
        />
        <div
          className="mt-12 grid gap-4"
          style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))' }}
        >
          {FEATURES.map((f, i) => (
            <motion.div
              key={f.title}
              className="glass-card glass-card-hover"
              style={{ padding: 24 }}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.45, delay: i * 0.05, ease: 'easeOut' }}
            >
              <div
                aria-hidden="true"
                style={{
                  width: 44, height: 44, borderRadius: 12,
                  display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                  background: 'linear-gradient(135deg, rgba(204,120,92,0.12), rgba(138,111,92,0.12))',
                  border: '1px solid var(--border-default)',
                  color: 'var(--accent-cyan)', marginBottom: 16,
                }}
              >
                <f.Icon size={22} />
              </div>
              <h3 style={{ fontSize: '1.1rem', marginBottom: 8 }}>{f.title}</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.92rem', lineHeight: 1.55 }}>
                {f.body}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

const STEPS = [
  {
    n: '01',
    title: 'Connect Kaggle',
    body: 'One-click sign-in with your Kaggle account. No password ever leaves your browser.',
  },
  {
    n: '02',
    title: 'Pick a competition',
    body: 'Browse active and past simulation competitions. Sort by deadline, prize, or popularity.',
  },
  {
    n: '03',
    title: 'Queue & download',
    body: 'Filter the submissions you want, queue them, and watch the live progress bar do the work.',
  },
] as const

function HowItWorks(): JSX.Element {
  return (
    <section
      id="how"
      style={{
        padding: 'clamp(80px, 12vw, 140px) 0',
        background: 'var(--bg-surface)',
        borderTop: '1px solid var(--border-subtle)',
        borderBottom: '1px solid var(--border-subtle)',
      }}
    >
      <div className="mx-auto px-4 md:px-8" style={{ maxWidth: 1200 }}>
        <SectionHeader
          eyebrow="How it works"
          title={<>From login to insight in <span className="gradient-text">under a minute</span>.</>}
        />
        <div
          className="mt-12 grid gap-4"
          style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(260px, 1fr))' }}
        >
          {STEPS.map((s, i) => (
            <motion.div
              key={s.n}
              className="glass-card"
              style={{ padding: 28, position: 'relative' }}
              initial={{ opacity: 0, y: 16 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, margin: '-80px' }}
              transition={{ duration: 0.45, delay: i * 0.08, ease: 'easeOut' }}
            >
              <div
                className="mono gradient-text"
                style={{ fontSize: '2rem', fontWeight: 700, marginBottom: 14 }}
              >
                {s.n}
              </div>
              <h3 style={{ fontSize: '1.15rem', marginBottom: 8 }}>{s.title}</h3>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.92rem', lineHeight: 1.55 }}>
                {s.body}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

function CTA(): JSX.Element {
  return (
    <section style={{ padding: 'clamp(80px, 12vw, 140px) 0' }}>
      <div className="mx-auto px-4 md:px-8" style={{ maxWidth: 980 }}>
        <div
          className="glass-card mesh-bg-animated relative"
          style={{
            padding: 'clamp(40px, 6vw, 72px)',
            textAlign: 'center',
            overflow: 'hidden',
          }}
        >
          <h2
            style={{
              fontFamily: 'var(--font-display)',
              fontSize: 'clamp(2rem, 4.5vw, 3.25rem)',
              letterSpacing: '-0.025em',
              marginBottom: 16,
              lineHeight: 1.05,
            }}
          >
            Ready to study smarter?
          </h2>
          <p
            className="mx-auto"
            style={{
              color: 'var(--text-primary)', opacity: 0.78,
              fontSize: '1.05rem', maxWidth: 560, marginBottom: 32, lineHeight: 1.55,
            }}
          >
            Join Kagglers using Replay Analytics to find the games that move the leaderboard.
          </p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <Link to="/login" className="btn-primary-glow btn-lg">Sign in with Kaggle</Link>
            <a href="#features" className="btn-ghost">Learn more</a>
          </div>
        </div>
      </div>
    </section>
  )
}

function Footer(): JSX.Element {
  return (
    <footer
      style={{
        borderTop: '1px solid var(--border-subtle)',
        padding: '32px 0',
        background: 'var(--bg-base)',
      }}
    >
      <div
        className="mx-auto flex flex-col md:flex-row items-center justify-between gap-4 px-4 md:px-8"
        style={{ maxWidth: 1200 }}
      >
        <div className="flex items-center gap-2" style={{ fontFamily: 'var(--font-mono)' }}>
          <span aria-hidden="true" style={{ color: 'var(--accent-cyan)', display: 'inline-flex' }}><BoltIcon size={18} /></span>
          <span style={{ color: 'var(--text-muted)', fontSize: '0.85rem' }}>
            replay.analytics · independent project
          </span>
        </div>
        <div className="flex items-center gap-6" style={{ fontSize: '0.85rem', color: 'var(--text-faint)' }}>
          <span>Not affiliated with Kaggle Inc.</span>
          <a
            href="https://www.kaggle.com"
            target="_blank"
            rel="noreferrer noopener"
            className="inline-flex items-center gap-1"
            style={{ color: 'var(--text-muted)' }}
          >
            kaggle.com
            <ArrowUpRightIcon size={13} />
          </a>
        </div>
      </div>
    </footer>
  )
}

function SectionHeader({
  eyebrow, title, subtitle,
}: { eyebrow: string; title: JSX.Element; subtitle?: string }): JSX.Element {
  return (
    <div className="text-center mx-auto" style={{ maxWidth: 720 }}>
      <div
        className="mono"
        style={{ color: 'var(--accent-cyan)', textTransform: 'uppercase', letterSpacing: '0.15em', fontSize: '0.78rem', marginBottom: 12 }}
      >
        {eyebrow}
      </div>
      <h2
        style={{
          fontFamily: 'var(--font-display)',
          fontSize: 'clamp(1.9rem, 4vw, 3rem)',
          letterSpacing: '-0.025em',
          lineHeight: 1.08,
          fontWeight: 700,
        }}
      >
        {title}
      </h2>
      {subtitle && (
        <p
          className="mx-auto mt-4"
          style={{ color: 'var(--text-muted)', fontSize: '1rem', maxWidth: 560, lineHeight: 1.55 }}
        >
          {subtitle}
        </p>
      )}
    </div>
  )
}
