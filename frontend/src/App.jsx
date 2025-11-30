import { useState } from "react";
import "./App.css";

function App() {
  const [cvFile, setCvFile] = useState(null);
  const [targetRole, setTargetRole] = useState("Azure Cloud Engineer");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const handleSubmit = async () => {
    if (!cvFile) {
      setError("Please upload a PDF first.");
      return;
    }
    setError("");
    setLoading(true);
    setResult(null);

    try {
      const resp = await fetch("/api/analyze_resume", {
        method: "POST",
        headers: {
          "x-target-role": targetRole,
        },
        body: cvFile,
      });

      const json = await resp.json();
      setResult(json);
    } catch (err) {
      console.error(err);
      setError("Error calling backend: " + err.message);
    }

    setLoading(false);
  };

  const analysis = result?.analysis || null;
  const score =
    typeof analysis?.overall_score === "number"
      ? Math.max(0, Math.min(100, analysis.overall_score))
      : null;

  const strengths = Array.isArray(analysis?.strengths) ? analysis.strengths : [];
  const weaknesses = Array.isArray(analysis?.weaknesses) ? analysis.weaknesses : [];
  const missingKeywords = Array.isArray(analysis?.missing_keywords)
    ? analysis.missing_keywords
    : [];
  const suggestions = Array.isArray(analysis?.improvement_suggestions)
    ? analysis.improvement_suggestions
    : [];

  return (
    <div className="app-root">
      <header className="app-header">
        <div>
          <h1>AI Resume Analyzer</h1>
          <p className="app-subtitle">
            Upload your CV and get tailored feedback for a specific role.
          </p>
        </div>
      </header>

      <main className="app-main">
        <section className="card">
          <h2 className="card-title">1. Upload & Configure</h2>

          <div className="field">
            <label className="field-label">Target job role</label>
            <input
              type="text"
              className="field-input"
              value={targetRole}
              onChange={(e) => setTargetRole(e.target.value)}
              placeholder="e.g. Azure Cloud Security Architect"
            />
          </div>

          <div className="field">
            <label className="field-label">CV (PDF only)</label>
            <input
              type="file"
              accept="application/pdf"
              onChange={(e) => setCvFile(e.target.files?.[0] || null)}
              className="field-file"
            />
            {cvFile && (
              <p className="field-helper">
                Selected: <strong>{cvFile.name}</strong> ({Math.round(cvFile.size / 1024)} KB)
              </p>
            )}
          </div>

          {error && <div className="alert alert-error">{error}</div>}

          <button
            className="btn-primary"
            onClick={handleSubmit}
            disabled={loading}
          >
            {loading ? (
              <span className="btn-spinner">
                <span className="spinner" /> Analyzing…
              </span>
            ) : (
              "Analyze my CV"
            )}
          </button>
        </section>

        {result && (
          <section className="results-grid">
            {/* Summary + score */}
            <div className="card card-highlight">
              <div className="card-header-row">
                <h2 className="card-title">2. Overall Assessment</h2>
                {score !== null && (
                  <div className="score-badge">
                    <span className="score-number">{score}</span>
                    <span className="score-label">/100</span>
                  </div>
                )}
              </div>

              <p className="result-role">
                Target role: <strong>{result.targetRole}</strong>
              </p>

              <p className="result-summary">
                {analysis?.summary ||
                  "No summary provided. Check the raw analysis below."}
              </p>

              <div className="meta-row">
                <div className="meta-item">
                  <span className="meta-label">Uploaded at</span>
                  <span className="meta-value">
                    {new Date(result.uploadedAt).toLocaleString()}
                  </span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Blob URL</span>
                  <a
                    href={result.blobUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="meta-link"
                  >
                    Open in Azure Blob
                  </a>
                </div>
              </div>
            </div>

            {/* Strengths / Weaknesses */}
            <div className="card">
              <h2 className="card-title">3. Strengths & Weaknesses</h2>
              <div className="two-cols">
                <div>
                  <h3 className="pill pill-good">Strengths</h3>
                  {strengths.length === 0 && (
                    <p className="empty-text">No strengths detected.</p>
                  )}
                  <ul className="list">
                    {strengths.map((s, idx) => (
                      <li key={idx}>{s}</li>
                    ))}
                  </ul>
                </div>
                <div>
                  <h3 className="pill pill-bad">Weaknesses</h3>
                  {weaknesses.length === 0 && (
                    <p className="empty-text">No weaknesses detected.</p>
                  )}
                  <ul className="list list-weak">
                    {weaknesses.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>

            {/* Missing keywords */}
            <div className="card">
              <h2 className="card-title">4. Missing Keywords</h2>
              {missingKeywords.length === 0 ? (
                <p className="empty-text">
                  No missing keywords reported. Nice coverage!
                </p>
              ) : (
                <div className="chips">
                  {missingKeywords.map((k, idx) => (
                    <span key={idx} className="chip">
                      {k}
                    </span>
                  ))}
                </div>
              )}
            </div>

            {/* Suggestions */}
            <div className="card">
              <h2 className="card-title">5. Improvement Suggestions</h2>
              {suggestions.length === 0 ? (
                <p className="empty-text">
                  No suggestions provided. You can still refine your prompt to
                  get more detailed tips.
                </p>
              ) : (
                <ol className="list ordered">
                  {suggestions.map((s, idx) => (
                    <li key={idx}>{s}</li>
                  ))}
                </ol>
              )}
            </div>

            {/* Raw JSON (debug / advanced) */}
            <div className="card">
              <details>
                <summary className="card-title small">Raw response (debug)</summary>
                <pre className="json-preview">
                  {JSON.stringify(result, null, 2)}
                </pre>
              </details>
            </div>
          </section>
        )}
      </main>
    </div>
  );
}

export default App;
