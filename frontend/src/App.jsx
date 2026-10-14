import { useEffect, useRef, useState } from 'react'
import { verifyQr } from './api.js'

const MAX_BYTES = 4 * 1024 * 1024
const ALLOWED = ['image/png', 'image/jpeg', 'image/jpg']

const SAMPLES = [
  { file: '1_safe_demo.png', label: 'Clean merchant QR', hint: 'Expected: Safe' },
  { file: '2_risky_demo.png', label: 'Name mismatch + refund note', hint: 'Expected: Risky' },
  { file: '3_fraud_demo.png', label: 'Demo flagged “prize” account', hint: 'Expected: Likely Fraud' },
  { file: '4_unsupported_demo.png', label: 'QR with a web link', hint: 'Expected: Unable to Verify' },
  { file: '5_unreadable_demo.png', label: 'Image with no QR', hint: 'Expected: Unable to Verify' },
]

const VERDICTS = {
  SAFE: { label: 'Safe', tone: 'safe', icon: '✓', sub: 'No significant warning signs detected' },
  RISKY: { label: 'Risky', tone: 'risky', icon: '!', sub: 'Verify before paying' },
  LIKELY_FRAUD: { label: 'Likely Fraud', tone: 'fraud', icon: '✕', sub: 'Do not pay' },
  UNABLE_TO_VERIFY: { label: 'Unable to Verify', tone: 'unknown', icon: '?', sub: 'Not enough valid information' },
}

const DISCLAIMER =
  'This result is a risk assessment based on available information, not a guarantee that the payment is legitimate. Verify the recipient and amount in your official UPI app before authorizing payment.'

export default function App() {
  const [file, setFile] = useState(null)
  const [preview, setPreview] = useState(null)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef(null)
  const resultRef = useRef(null)

  useEffect(() => () => preview && URL.revokeObjectURL(preview), [preview])

  function selectFile(f) {
    setResult(null)
    setError('')
    if (!f) return
    if (!ALLOWED.includes(f.type)) {
      setError('Unsupported file type. Please upload a PNG, JPG or JPEG image.')
      return
    }
    if (f.size > MAX_BYTES) {
      setError('File is too large. The maximum size is 4 MB.')
      return
    }
    setFile(f)
    setPreview(URL.createObjectURL(f))
  }

  async function loadSample(name) {
    try {
      const res = await fetch(`/samples/${name}`)
      if (!res.ok) throw new Error()
      const blob = await res.blob()
      selectFile(new File([blob], name, { type: 'image/png' }))
    } catch {
      setError('Could not load the sample image.')
    }
  }

  async function analyse() {
    if (!file) return
    setLoading(true)
    setError('')
    setResult(null)
    try {
      setResult(await verifyQr(file))
      setTimeout(() => resultRef.current?.focus(), 50)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  function reset() {
    setFile(null)
    setPreview(null)
    setResult(null)
    setError('')
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <>
      <header className="topbar">
        <div className="wrap topbar-inner">
          <div className="brand">
            <span className="brand-mark" aria-hidden="true">◈</span>
            <span>QR Shield</span>
          </div>
          <span className="badge-proto">Prototype · Pre-payment check</span>
        </div>
      </header>

      <main className="wrap">
        <section className="hero">
          <h1>Verify Before You Pay</h1>
          <p>
            Upload a UPI QR code or screenshot. We decode it, check the payment details and explain any
            warning signs — <strong>before</strong> you open your UPI app. We never make payments or ask for your PIN.
          </p>
          <ol className="steps" aria-label="How it works">
            {['Upload QR', 'Decode', 'Validate', 'Detect signals', 'Verdict'].map((s, i) => (
              <li key={s}><span>{i + 1}</span>{s}</li>
            ))}
          </ol>
        </section>

        <div className="grid">
          {/* Stage 1: Upload */}
          <section className="card" aria-labelledby="upload-h">
            <h2 id="upload-h">1 · Upload QR image</h2>

            <label
              className={`dropzone ${dragging ? 'drag' : ''}`}
              onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); selectFile(e.dataTransfer.files[0]) }}
            >
              <input
                ref={inputRef}
                type="file"
                accept="image/png,image/jpeg"
                className="sr-only"
                onChange={(e) => selectFile(e.target.files[0])}
                aria-describedby="upload-help"
              />
              {preview ? (
                <div className="preview">
                  <img src={preview} alt="Uploaded QR code preview" />
                  <span className="filename" title={file?.name}>{file?.name}</span>
                </div>
              ) : (
                <div className="dz-empty">
                  <span className="dz-icon" aria-hidden="true">⬆</span>
                  <strong>Click to choose</strong> or drag an image here
                  <span id="upload-help" className="muted small">PNG, JPG or JPEG · max 4 MB</span>
                </div>
              )}
            </label>

            {error && <div className="alert" role="alert">{error}</div>}

            <div className="actions">
              <button className="btn primary" onClick={analyse} disabled={!file || loading}>
                {loading ? <><span className="spinner" aria-hidden="true" /> Analysing…</> : 'Decode & Check Risk'}
              </button>
              {file && <button className="btn ghost" onClick={reset} disabled={loading}>Clear</button>}
            </div>

            <div className="samples">
              <h3>Try a synthetic demo QR</h3>
              <p className="muted small">These use the fictional <code>@demobank</code> handle and are not real accounts.</p>
              <ul>
                {SAMPLES.map((s) => (
                  <li key={s.file}>
                    <button className="sample" onClick={() => loadSample(s.file)} disabled={loading}>
                      <span>{s.label}</span>
                      <span className="muted small">{s.hint}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </section>

          {/* Stages 2-4: Results */}
          <section className="card result-col" aria-labelledby="result-h" aria-live="polite" aria-busy={loading}>
            <h2 id="result-h">2 · Analysis</h2>
            {loading && <Loading />}
            {!loading && !result && <EmptyState />}
            {!loading && result && <Result data={result} focusRef={resultRef} />}
          </section>
        </div>

        <p className="disclaimer" role="note"><strong>Disclaimer:</strong> {DISCLAIMER}</p>
      </main>

      <footer className="wrap footer muted small">
        B.Tech project prototype · Rule-based detection (no ML model) · Demo indicators are synthetic.
      </footer>
    </>
  )
}

function Loading() {
  return (
    <div className="state">
      <span className="spinner lg" aria-hidden="true" />
      <p>Decoding QR and running checks…</p>
    </div>
  )
}

function EmptyState() {
  return (
    <div className="state">
      <span className="state-icon" aria-hidden="true">⌗</span>
      <p><strong>No QR analysed yet</strong></p>
      <p className="muted small">Upload an image or pick a demo QR, then press “Decode &amp; Check Risk”.</p>
    </div>
  )
}

function Result({ data, focusRef }) {
  const v = VERDICTS[data.verdict] ?? VERDICTS.UNABLE_TO_VERIFY
  const p = data.payment
  const warnings = (data.signals || []).filter((s) => s.severity !== 'info')
  const infos = (data.signals || []).filter((s) => s.severity === 'info')

  return (
    <div className="result">
      <div className={`verdict ${v.tone}`} tabIndex={-1} ref={focusRef}>
        <span className="verdict-icon" aria-hidden="true">{v.icon}</span>
        <div>
          <div className="verdict-label">{v.label}</div>
          <div className="verdict-sub">{v.sub}</div>
        </div>
        {data.risk_score != null && (
          <div className="score" aria-label={`Risk score ${data.risk_score} out of 100`}>
            <span>{data.risk_score}</span><small>/100 risk</small>
          </div>
        )}
      </div>

      <p className="explanation">{data.explanation}</p>

      {p && (
        <div className="subcard">
          <h3>Decoded payment details</h3>
          <dl className="details">
            <Field k="Payee UPI ID" v={p.payee_vpa} mono />
            <Field k="Payee name" v={p.payee_name} />
            <Field k="Amount" v={p.amount ? `${p.currency === 'INR' || !p.currency ? '₹' : ''}${p.amount}` : null} />
            <Field k="Currency" v={p.currency} />
            <Field k="Note" v={p.note} />
            {p.merchant_code && <Field k="Merchant code" v={p.merchant_code} />}
          </dl>
        </div>
      )}

      {warnings.length > 0 && (
        <div className="subcard">
          <h3>Warning indicators ({warnings.length})</h3>
          <ul className="signals">
            {warnings.map((s, i) => (
              <li key={i} className={`sig ${s.severity}`}>
                <span className="sev">{s.severity}</span>
                <div><strong>{s.title}</strong><p>{s.detail}</p></div>
              </li>
            ))}
          </ul>
        </div>
      )}
      {warnings.length === 0 && data.verdict === 'SAFE' && (
        <div className="subcard"><h3>Warning indicators</h3><p className="muted">None detected by the available checks.</p></div>
      )}

      {infos.length > 0 && (
        <ul className="infos muted small">
          {infos.map((s, i) => <li key={i}>ⓘ {s.detail}</li>)}
        </ul>
      )}

      <div className="subcard">
        <h3>Recommended next steps</h3>
        <ol className="next">{data.next_steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
      </div>

      {data.decoded_payload && (
        <details className="raw">
          <summary>Show raw decoded content</summary>
          <p className="muted small">Shown as text only — links are never opened automatically.</p>
          <code>{data.decoded_payload}</code>
        </details>
      )}
    </div>
  )
}

function Field({ k, v, mono }) {
  return (
    <>
      <dt>{k}</dt>
      <dd className={mono ? 'mono' : ''}>{v ?? <span className="muted">Not provided</span>}</dd>
    </>
  )
}
