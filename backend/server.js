const express = require("express");

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "32kb" }));

const allowedOrigins = (process.env.ALLOWED_ORIGINS || "https://gurraslut-design.github.io")
  .split(",").map(value => value.trim()).filter(Boolean);

app.use((req, res, next) => {
  const origin = req.get("origin");
  if (origin && (!allowedOrigins.length || allowedOrigins.includes(origin))) {
    res.setHeader("Access-Control-Allow-Origin", origin);
    res.setHeader("Vary", "Origin");
    res.setHeader("Access-Control-Allow-Methods", "GET,POST,OPTIONS");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
  }
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

app.get("/api/health", (_req, res) => {
  res.json({
    ok: true,
    service: "AI Capital Lab backend",
    modelConfigured: Boolean(process.env.OPENAI_API_KEY && process.env.OPENAI_MODEL),
    mode: "planning-only",
    realOrdersEnabled: false
  });
});

async function runTeam(topic) {
  if (!process.env.OPENAI_API_KEY || !process.env.OPENAI_MODEL) {
    const error = new Error("Backend saknar OPENAI_API_KEY eller OPENAI_MODEL. Lägg till dem som server-hemligheter hos driftleverantören.");
    error.status = 503;
    throw error;
  }

  // One model request produces distinct role perspectives and a final synthesis.
  // This avoids five serial requests timing out on mobile/free hosting and lowers cost.
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 90000);
  let response;
  try {
    response = await fetch("https://api.openai.com/v1/responses", {
      method: "POST",
      signal: controller.signal,
      headers: {
        "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify({
        model: process.env.OPENAI_MODEL,
        instructions: [
          "Du är AI Capital Lab, ett samordnat AI-team. Svara på svenska.",
          "Analysera uppgiften genom fyra tydligt åtskilda perspektiv: coordinator, analyst, developer och reviewer.",
          "Coordinator: mål, plan och prioriterat nästa steg.",
          "Analyst: fakta som är kända, antaganden, osäkerheter och vad som behöver verifieras.",
          "Developer: praktisk lösning eller implementeringsplan; påstå inte att kod/system har ändrats.",
          "Reviewer: oberoende kritisk granskning av risker, fel, saknade bevis och överdrivna påståenden.",
          "Final: samlad rekommendation som tar hänsyn till reviewer-granskningen.",
          "Svara med ett JSON-objekt med strängfälten coordinator, analyst, developer, reviewer och final. Skriv ordet JSON i svaret och använd inga markdown-staket.",
          "Utför inga externa åtgärder och påstå inte att arbete har utförts om det bara föreslås."
        ].join("\n"),
        input: `Please return JSON for this task.\n\n${topic}`,
        store: false
      })
    });
  } catch (error) {
    if (error.name === "AbortError") {
      const timeoutError = new Error("AI-svaret tog för lång tid. Försök igen senare.");
      timeoutError.status = 504;
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error?.message || `Modell-anrop misslyckades (${response.status}).`);
    error.status = response.status === 429 ? 429 : 502;
    throw error;
  }

  const outputText = data.output_text || (data.output || [])
    .flatMap(item => item.content || [])
    .filter(item => item.type === "output_text")
    .map(item => item.text)
    .join("\n");
  if (!outputText.trim()) {
    const error = new Error("Modellen returnerade inget textresultat.");
    error.status = 502;
    throw error;
  }

  let report;
  try {
    const cleanedOutput = outputText.trim().replace(/^```(?:json)?\s*/i, "").replace(/\s*```$/, "");
    report = JSON.parse(cleanedOutput);
  } catch (_) {
    const error = new Error("Modellen returnerade ett format som inte kunde läsas. Försök igen.");
    error.status = 502;
    throw error;
  }

  for (const field of ["coordinator", "analyst", "developer", "reviewer", "final"]) {
    if (typeof report[field] !== "string" || !report[field].trim()) {
      const error = new Error("AI-teamet returnerade en ofullständig rapport. Försök igen.");
      error.status = 502;
      throw error;
    }
  }
  return report;
}

app.post("/api/team-run", async (req, res) => {
  const topic = typeof req.body?.topic === "string" ? req.body.topic.trim() : "";
  if (!topic || topic.length > 5000) {
    return res.status(400).json({ error: "Skriv en uppgift på 1–5000 tecken." });
  }

  try {
    const report = await runTeam(topic);
    res.json({
      mode: "real-model-run",
      realOrdersEnabled: false,
      completedAt: new Date().toISOString(),
      topic,
      agents: {
        coordinator: report.coordinator,
        analyst: report.analyst,
        developer: report.developer,
        reviewer: report.reviewer
      },
      final: report.final
    });
  } catch (error) {
    res.status(error.status || 502).json({ error: error.message || "AI-teamet kunde inte slutföra körningen." });
  }
});

app.get("/", (_req, res) => {
  res.type("text/plain").send("AI Capital Lab backend. See /api/health.");
});

const port = Number(process.env.PORT) || 3000;
app.listen(port, "0.0.0.0", () => {
  console.log(`AI Capital Lab backend listening on port ${port}`);
});
