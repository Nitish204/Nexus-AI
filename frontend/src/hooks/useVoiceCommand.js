import { useCallback, useRef, useState } from "react";

/**
 * Wraps the browser's native SpeechRecognition API (Chrome/Edge; no
 * external service or API key needed) so voice commands transcribe to
 * text and feed straight into the same /command endpoint typed
 * commands use — the backend never knows the difference.
 */
export function useVoiceCommand(onTranscript) {
  const [listening, setListening] = useState(false);
  const [supported] = useState(() => "webkitSpeechRecognition" in window || "SpeechRecognition" in window);
  const recognitionRef = useRef(null);

  const start = useCallback(() => {
    if (!supported) return;
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = "en-US";

    recognition.onstart = () => setListening(true);
    recognition.onend = () => setListening(false);
    recognition.onerror = () => setListening(false);
    recognition.onresult = (event) => {
      const transcript = event.results[0][0].transcript;
      onTranscript(transcript);
    };

    recognitionRef.current = recognition;
    recognition.start();
  }, [supported, onTranscript]);

  const stop = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  return { start, stop, listening, supported };
}
