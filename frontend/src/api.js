// Thin API client. Additional verification types (UPI ID, payment link)
// can be added here as new functions hitting new endpoints.

export async function verifyQr(file) {
  const form = new FormData()
  form.append('file', file)
  let res
  try {
    res = await fetch('/api/verify/qr', { method: 'POST', body: form })
  } catch {
    throw new Error('Could not reach the verification server. Is the backend running on port 8000?')
  }
  let body
  try {
    body = await res.json()
  } catch {
    throw new Error(`The server returned an unexpected response (HTTP ${res.status}).`)
  }
  return body
}
