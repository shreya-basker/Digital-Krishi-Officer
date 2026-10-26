// Chat with the Agrisathi assistant. The OpenAI call happens on the server,
// which also adds the farmer's farm context (crop, stage, soil, weather, prices).

const SPEECH_LANG = { en: "en-IN", ml: "ml-IN", hi: "hi-IN" };

document.addEventListener("DOMContentLoaded", async () => {
  if (!Api.requireAuth()) return;

  const queryInput = document.getElementById("queryInput");
  const submitBtn = document.getElementById("submitBtn");
  const voiceBtn = document.getElementById("voiceBtn");
  const ttsBtn = document.getElementById("ttsBtn");
  const imageInput = document.getElementById("imageInput");
  const imagePreview = document.getElementById("imagePreview");
  const chatContainer = document.getElementById("chatContainer");
  const language = Api.user()?.language || "en";

  let uploadedImage = null;
  let uploadedMime = "image/jpeg";
  let farmId = null;

  try {
    const farm = await Api.currentFarm();
    farmId = farm?.id ?? null;
  } catch { /* chat still works without farm context */ }

  // ✅ Preview uploaded image
  imageInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        uploadedImage = reader.result.split(",")[1]; // Base64
        uploadedMime = file.type || "image/jpeg";
        imagePreview.src = reader.result;
        imagePreview.style.display = "block";
      };
      reader.readAsDataURL(file);
    }
  });

  function addChatBubble(text, sender, time = new Date()) {
    const bubble = document.createElement("div");
    bubble.className = `chat-bubble ${sender}`;
    bubble.innerText = text;
    const stamp = document.createElement("div");
    stamp.className = "timestamp";
    stamp.innerText = new Date(time).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    bubble.appendChild(stamp);
    chatContainer.appendChild(bubble);
    chatContainer.scrollTop = chatContainer.scrollHeight;
    return bubble;
  }

  // Show recent conversation
  try {
    const history = await Api.get("/chat/history?limit=10");
    history.forEach(q => {
      addChatBubble(q.text || "📷 Image uploaded", "user", q.created_at);
      addChatBubble(q.answer, "ai", q.created_at);
    });
  } catch { /* ignore */ }

  // ✅ Ask the assistant
  async function askQuery() {
    const userQuery = queryInput.value.trim();
    if (!userQuery && !uploadedImage) {
      alert("Please enter a query or upload an image!");
      return;
    }

    if (userQuery) addChatBubble(userQuery, "user");
    if (uploadedImage) addChatBubble("📷 Image uploaded", "user");
    const processingMsg = addChatBubble("⏳ Thinking…", "ai");
    submitBtn.disabled = true;

    try {
      const data = await Api.post("/chat", {
        text: userQuery, image_base64: uploadedImage, image_mime: uploadedMime, farm_id: farmId,
      });
      processingMsg.remove();
      addChatBubble(data.answer, "ai");
    } catch (err) {
      console.error("Error:", err);
      processingMsg.firstChild.textContent = "❌ " + err.message;
    } finally {
      submitBtn.disabled = false;
    }

    queryInput.value = "";
    uploadedImage = null;
    imageInput.value = "";
    imagePreview.style.display = "none";
  }

  // ✅ Voice Input
  function startVoice() {
    const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!Recognition) { alert("Voice input is not supported in this browser."); return; }
    const recognition = new Recognition();
    recognition.lang = SPEECH_LANG[language] || "en-IN";
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      queryInput.value = event.results[0][0].transcript;
      askQuery();
    };

    recognition.start();
  }

  // ✅ Read Latest AI Response
  function readAnswer() {
    const aiBubbles = chatContainer.querySelectorAll(".chat-bubble.ai");
    if (!aiBubbles.length) return;

    const latestAnswer = aiBubbles[aiBubbles.length - 1].firstChild.textContent;
    if (!latestAnswer || latestAnswer.startsWith("⏳") || latestAnswer.startsWith("❌")) return;

    const utter = new SpeechSynthesisUtterance(latestAnswer);
    utter.lang = SPEECH_LANG[language] || "en-IN";
    speechSynthesis.speak(utter);
  }

  // ✅ Event Listeners
  submitBtn.addEventListener("click", askQuery);
  queryInput.addEventListener("keydown", (e) => { if (e.key === "Enter") askQuery(); });
  voiceBtn.addEventListener("click", startVoice);
  ttsBtn.addEventListener("click", readAnswer);
});
