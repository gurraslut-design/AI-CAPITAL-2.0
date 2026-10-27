const express = require("express");

const app = express();
app.disable("x-powered-by");
app.use(express.json({ limit: "32kb" }));

const allowedOrigins = (process.env.ALLOWED_ORIGINS || "")
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
    modelConfigured: Boolean(process.env.OPENAI_API_KEY),
    mode: "planning-only",
    realOrdersEnabled: false
  });
});

async function askModel({ role, instructions, input }) {
  if (!process.env.OPENAI_API_KEY) {
    const error = new Error("Backend saknar OPENAI_API_KEY. Lägg till nyckeln som en server-hemlighet hos driftleverantören.");
    error.status = 503;
    throw error;
  }

  const response = await fetch("https://api.openai.com/v1/responses", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${process.env.OPENAI_API_KEY}`,
      "Content-Type": "application/json"
    },
    body: JSON.stringify({
      model: process.env.OPENAI_MODEL || "gpt-5.6",
      instructions: `Du är ${role} i AI Capital Lab. ${instructions} Svara på svenska. Var tydlig med fakta, antaganden och osäkerhet. Utför inga externa åtgärder.`,
      input,
      store: false
    })
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const error = new Error(data.error?.message || `Modell-anrop misslyckades (${response.status}).`);
    error.status = response.status === 429 ? 429 : 502;
    throw error;
  }

  const text = data.output_text || (data.output || [])
    .flatMap(item => item.content || [])
    .filter(item => item.type === "output_text")
    .map(item => item.text)
    .join("\n");
  if (!text.trim()) {
    const error = new Error("Modellen returnerade inget textresultat.");
    error.status = 502;
    throw error;
  }
  return text.trim();
}

app.post("/api/team-run", async (req, res) => {
  const topic = typeof req.body?.topic === "string" ? req.body.topic.trim() : "";
  if (!topic || topic.length > 5000) {
    return res.status(400).json({ error: "Skriv en uppgift på 1–5000 tecken." });
  }

  try {
    const coordinator = await askModel({
      role: "Coordinator",
      instructions: "Gör en konkret plan med mål, delsteg och mätbart resultat. Hitta inte på att arbete redan utförts.",
      input: topic
    });
    const analyst = await askModel({
      role: "Analyst",
      instructions: "Analysera Coordinator-planen. Skilj mellan kända fakta, antaganden, vad som måste kontrolleras och mätbara kriterier.",
      input: `Ursprunglig uppgift:\n${topic}\n\nCoordinator-plan:\n${coordinator}`
    });
    const developer = await askModel({
      role: "Developer",
      instructions: "Föreslå en praktisk implementerings- eller testplan. Markera uttryckligen vad som inte har utförts och undvik att påstå att kod eller system har ändrats.",
      input: `Uppgift:\n${topic}\n\nPlan:\n${coordinator}\n\nAnalys:\n${analyst}`
    });
    const reviewer = await askModel({
      role: "Independent Reviewer",
      instructions: "Granska kritiskt tidigare svar. Leta efter fel, risker, saknade bevis, säkerhetsproblem och överdrivna påståenden. Ge tydligt godkänd/inte godkänd med skäl.",
      input: `Uppgift:\n${topic}\n\nPlan:\n${coordinator}\n\nAnalys:\n${analyst}\n\nUtvecklarens förslag:\n${developer}`
    });
    const final = await askModel({
      role: "Coordinator",
      instructions: "Sammanställ teamets svar. Ta med rekommenderat nästa steg, kvarstående osäkerheter och reviewer-invändningar. Påstå inte att föreslagna åtgärder redan utförts.",
      input: `Uppgift:\n${topic}\n\nPlan:\n${coordinator}\n\nAnalys:\n${analyst}\n\nUtveckling:\n${developer}\n\nOberoende granskning:\n${reviewer}`
    });

    res.json({
      mode: "real-model-calls",
      realOrdersEnabled: false,
      completedAt: new Date().toISOString(),
      topic,
      agents: { coordinator, analyst, developer, reviewer },
      final
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
