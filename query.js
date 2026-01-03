

// ✅ Firebase Config
const firebaseConfig = {
  apiKey: "AIzaSyDNCIkLl0TUK6NDeFUYg9JczI_m_H2KUNI",
  authDomain: "digital-krishi-officer-9b3f4.firebaseapp.com",
  projectId: "digital-krishi-officer-9b3f4",
  storageBucket: "digital-krishi-officer-9b3f4.appspot.com",
  messagingSenderId: "552837625635",
  appId: "1:552837625635:web:eedd75eecfb5a823d27e96"
};

// ✅ Initialize Firebase
firebase.initializeApp(firebaseConfig);
const db = firebase.firestore();

document.addEventListener("DOMContentLoaded", () => {
  const queryInput = document.getElementById("queryInput");
  const submitBtn = document.getElementById("submitBtn");
  const voiceBtn = document.getElementById("voiceBtn");
  const ttsBtn = document.getElementById("ttsBtn");
  const imageInput = document.getElementById("imageInput");
  const imagePreview = document.getElementById("imagePreview");
  const chatContainer = document.getElementById("chatContainer");

  let uploadedImage = null;

  // ✅ Preview uploaded image
  imageInput.addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = () => {
        uploadedImage = reader.result.split(",")[1]; // Base64
        imagePreview.src = reader.result;
        imagePreview.style.display = "block";
      };
      reader.readAsDataURL(file);
    }
  });

  // ✅ System Prompt for Gemini
const systemPrompt = `
You are a Digital Krishi Officer AI assistant. Your role is to give farmers quick, clear, and practical advice. 

Rules:
1. Answer only farming-related queries: crops, soil, irrigation, fertilizers, pests, seeds, government schemes, mandi prices, weather, pesticides, organic practices, and sustainable methods. 
2. Always keep answers short, clear, and easy to understand. Use bullet points or numbered lists where possible.
3. Language rule:
   - If the query is in Malayalam, reply in Malayalam.
   - Otherwise reply in simple English.
4. For location-based queries like "rice crops near me" or "pesticides near me":
   - Give general guidance (best practices, suitable conditions, common pesticides, etc.).
   - If exact local data is not available, tell for this location -- yehlanka, bangalore, karnataka, india as a default location."
5. If unsure, say: "Please consult your local Krishi Officer for exact guidance."
6. If the query is unrelated to farming, politely decline: "I can only help with farming-related questions."
7. If an image is provided:
   - Analyze it for crop health, soil, pest attack, or irrigation issues.
   - Give farming advice relevant to what is seen in the image.
8. If the query is empty but an image is provided → analyze the image and give advice.
9. If both query and image are empty → ask the farmer to type a query or upload an image.
10. Always encourage sustainable, eco-friendly, and cost-effective farming practices.
11. Be respectful, empathetic, and supportive toward farmers.
`;


function addChatBubble(text, sender) {
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${sender}`;
  bubble.innerText = text;
  chatContainer.appendChild(bubble);
  chatContainer.scrollTop = chatContainer.scrollHeight;
  return bubble;
}



  // ✅ Ask Gemini
  async function askQuery() {
    const userQuery = queryInput.value.trim();
    if (!userQuery && !uploadedImage) {
      alert("Please enter a query or upload an image!");
      return;
    }

    // Add user message to chat
    if (userQuery) addChatBubble(userQuery, "user");
    if (uploadedImage) addChatBubble("📷 Image uploaded", "user");
    const processingMsg = addChatBubble("...", "ai");


    try {
      const body = {
        contents: [
          {
            parts: [{ text: `${systemPrompt}\nFarmer query: ${userQuery}` }]
          }
        ]
      };

      if (uploadedImage) {
        body.contents[0].parts.push({
          inline_data: { mime_type: "image/jpeg", data: uploadedImage }
        });
      }

      const geminiResponse = await fetch(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash-latest:generateContent?key=" + GEMINI_API_KEY,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body)
        }
      );

      const data = await geminiResponse.json();
      console.log("Gemini Response:", data);

      let answer = "⚠️ No response received.";
      if (data.candidates && data.candidates[0].content.parts[0].text) {
        answer = data.candidates[0].content.parts[0].text;
      }

     // ✅ Add AI response bubble
         addChatBubble(answer, "ai");
  

      // ✅ Save to Firestore
      await db.collection("queries").add({
        query: userQuery || "Image only",
        answer,
        farmer: localStorage.getItem("farmerPhone") || "guest",
        timestamp: new Date()
      });

    } catch (err) {
      console.error("Error:", err);
      processingMsg.innerText = "❌ Error fetching response.";
    }

    queryInput.value = "";
    uploadedImage = null;
    imagePreview.style.display = "none";
  }

  // ✅ Voice Input
  function startVoice() {
    const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
    recognition.lang = "ml-IN";
    recognition.interimResults = false;

    recognition.onresult = (event) => {
      const voiceText = event.results[0][0].transcript;
      queryInput.value = voiceText;
      askQuery();
    };

    recognition.start();
  }

  // ✅ Read Latest AI Response
  function readAnswer() {
    const aiBubbles = chatContainer.querySelectorAll(".chat-bubble.ai");
    if (!aiBubbles.length) return;

    const latestAnswer = aiBubbles[aiBubbles.length - 1].innerText;
    if (!latestAnswer || latestAnswer.startsWith("⏳") || latestAnswer.startsWith("❌")) return;

    const utter = new SpeechSynthesisUtterance(latestAnswer);
    utter.lang = (localStorage.getItem("lang") === "ml") ? "ml-IN" : "en-US";
    speechSynthesis.speak(utter);
  }

  // ✅ Event Listeners
  submitBtn.addEventListener("click", askQuery);
  voiceBtn.addEventListener("click", startVoice);
  ttsBtn.addEventListener("click", readAnswer);

  // Expose for debug
  window.askQuery = askQuery;
});
