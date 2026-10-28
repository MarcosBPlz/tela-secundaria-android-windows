package com.telatablet.app;

import android.Manifest;
import android.app.Activity;
import android.content.ComponentName;
import android.content.Intent;
import android.content.pm.ResolveInfo;
import android.content.SharedPreferences;
import android.content.pm.ActivityInfo;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.speech.tts.TextToSpeech;
import android.speech.tts.UtteranceProgressListener;
import android.media.AudioManager;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;

import org.json.JSONArray;
import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

public class MainActivity extends Activity {
    private static final int PICK_MEDIA = 4102;
    private static final int RECORD_AUDIO_REQUEST = 4103;
    private WebView webView;
    private ValueCallback<android.net.Uri[]> uploadCallback;
    private SharedPreferences prefs;
    private SpeechRecognizer speechRecognizer;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());
    private final Handler watchdogHandler = new Handler(Looper.getMainLooper());
    private boolean voiceListening = false;
    private boolean activityVisible = true;
    private boolean pendingVoicePermission = false;
    private boolean recognizerActive = false;
    private TextToSpeech tts;
    private boolean ttsReady = false;
    private long lastLevelReport = 0;
    private float peakRms = -2f;
    private int silentMisses = 0;
    private boolean readyOnce = false;
    private String recognizerName = "padrão do aparelho";

    @Override public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY | View.SYSTEM_UI_FLAG_LAYOUT_STABLE |
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN);
        prefs = getSharedPreferences("tablet", MODE_PRIVATE);
        applyOrientation(prefs.getString("orientation", "auto"));
        setVolumeControlStream(AudioManager.STREAM_MUSIC);
        tts = new TextToSpeech(this, status -> {
            if (status != TextToSpeech.SUCCESS) return;
            int result = tts.setLanguage(new Locale("pt", "BR"));
            ttsReady = result != TextToSpeech.LANG_MISSING_DATA && result != TextToSpeech.LANG_NOT_SUPPORTED;
            tts.setSpeechRate(1.12f);
            tts.setOnUtteranceProgressListener(new UtteranceProgressListener() {
                @Override public void onStart(String id) { }
                @Override public void onDone(String id) { reportSpeakDone(); }
                @Override public void onError(String id) { reportSpeakDone(); }
            });
        });
        showConnectionScreen();
    }

    private void showConnectionScreen() {
        if (webView != null) stopVoiceCapture();
        LinearLayout layout = new LinearLayout(this);
        layout.setOrientation(LinearLayout.VERTICAL);
        layout.setPadding(36, 64, 36, 36);
        layout.setBackgroundColor(Color.rgb(18, 16, 27));
        TextView title = new TextView(this);
        title.setText("Conectar ao computador"); title.setTextColor(Color.WHITE); title.setTextSize(24);
        layout.addView(title);
        TextView hint = new TextView(this);
        hint.setText("Abra o Tela Tablet no Windows e informe o endereço de rede exibido, por exemplo http://192.168.1.10:47811");
        hint.setTextColor(Color.LTGRAY); hint.setTextSize(15); hint.setPadding(0, 16, 0, 16);
        layout.addView(hint);
        EditText address = new EditText(this);
        address.setSingleLine(true); address.setTextColor(Color.WHITE); address.setHintTextColor(Color.LTGRAY);
        address.setHint("http://192.168.x.x:47811");
        address.setText(prefs.getString("server", "")); layout.addView(address);
        Button connect = new Button(this); connect.setText("Conectar"); layout.addView(connect);
        TextView status = new TextView(this); status.setTextColor(Color.LTGRAY); layout.addView(status);
        connect.setOnClickListener(v -> {
            String url = address.getText().toString().trim();
            if (!url.startsWith("http://") && !url.startsWith("https://")) url = "http://" + url;
            while (url.endsWith("/")) url = url.substring(0, url.length() - 1);
            if (url.length() < 12) { status.setText("Informe o endereço mostrado no computador."); return; }
            prefs.edit().putString("server", url).apply();
            showPanel(url);
        });
        setContentView(layout);
    }

    private void showPanel(String url) {
        webView = new WebView(this);
        webView.setBackgroundColor(Color.rgb(18, 16, 27));
        webView.getSettings().setJavaScriptEnabled(true);
        webView.getSettings().setUserAgentString(webView.getSettings().getUserAgentString() + " TelaTabletAndroid");
        webView.getSettings().setDomStorageEnabled(true);
        webView.getSettings().setMediaPlaybackRequiresUserGesture(false);
        webView.addJavascriptInterface(new VoiceBridge(), "TelaTabletVoice");
        webView.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return !request.getUrl().getHost().equals(android.net.Uri.parse(url).getHost());
            }
        });
        webView.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<android.net.Uri[]> callback, FileChooserParams params) {
                if (uploadCallback != null) uploadCallback.onReceiveValue(null);
                uploadCallback = callback;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.setType("*/*"); pick.addCategory(Intent.CATEGORY_OPENABLE);
                startActivityForResult(Intent.createChooser(pick, "Escolher fundo"), PICK_MEDIA);
                return true;
            }
        });
        setContentView(webView);
        webView.loadUrl(url);
    }

    private final class VoiceBridge {
        @JavascriptInterface public void start() {
            runOnUiThread(() -> startVoiceCapture());
        }
        @JavascriptInterface public void stop() {
            runOnUiThread(() -> stopVoiceCapture());
        }
        @JavascriptInterface public boolean canSpeak() { return ttsReady; }
        @JavascriptInterface public String getOrientation() { return prefs.getString("orientation", "auto"); }
        @JavascriptInterface public void setOrientation(String mode) {
            String value = "landscape".equals(mode) || "portrait".equals(mode) ? mode : "auto";
            prefs.edit().putString("orientation", value).apply();
            runOnUiThread(() -> applyOrientation(value));
        }
        @JavascriptInterface public void speak(String text) {
            runOnUiThread(() -> {
                if (!ttsReady || tts == null) { reportSpeakDone(); return; }
                tts.speak(text, TextToSpeech.QUEUE_FLUSH, null, "reply");
            });
        }
        @JavascriptInterface public void stopSpeaking() {
            runOnUiThread(() -> { if (tts != null) tts.stop(); });
        }
    }

    private void applyOrientation(String mode) {
        if ("landscape".equals(mode)) setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_LANDSCAPE);
        else if ("portrait".equals(mode)) setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_SENSOR_PORTRAIT);
        else setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_FULL_USER);
    }

    private void startVoiceCapture() {
        if (!activityVisible) return;
        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            pendingVoicePermission = true;
            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, RECORD_AUDIO_REQUEST);
            return;
        }
        if (!SpeechRecognizer.isRecognitionAvailable(this)) {
            reportVoiceError("O reconhecimento de voz não está disponível neste tablet.");
            return;
        }
        voiceListening = true;
        if (recognizerActive) return; // já está ouvindo: o app mesmo reinicia a escuta
        if (speechRecognizer == null) {
            speechRecognizer = createBestRecognizer();
            speechRecognizer.setRecognitionListener(new RecognitionListener() {
                @Override public void onReadyForSpeech(Bundle params) {
                    peakRms = -2f;
                    if (!readyOnce) { readyOnce = true; reportVoiceStatus("Microfone ok (" + recognizerName + "). Pode falar."); }
                }
                @Override public void onBeginningOfSpeech() { }
                @Override public void onRmsChanged(float rmsdB) {
                    if (rmsdB > peakRms) peakRms = rmsdB;
                    long now = System.currentTimeMillis();
                    if (now - lastLevelReport < 120) return;
                    lastLevelReport = now;
                    float level = Math.max(0f, Math.min(1f, (rmsdB + 2f) / 12f));
                    reportLevel(level);
                }
                @Override public void onBufferReceived(byte[] buffer) { }
                @Override public void onEndOfSpeech() { }
                @Override public void onPartialResults(Bundle partialResults) {
                    ArrayList<String> matches = partialResults.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    if (matches != null && !matches.isEmpty() && matches.get(0).trim().length() > 0) reportVoiceStatus("Reconhecendo: " + matches.get(0));
                }
                @Override public void onEvent(int eventType, Bundle params) { }
                @Override public void onResults(Bundle results) {
                    recognizerActive = false;
                    silentMisses = 0;
                    reportLevel(0f);
                    ArrayList<String> matches = results.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION);
                    // Reabre o microfone logo em seguida, para não perder o que vier depois do "Chat"
                    scheduleRestart(80);
                    if (matches != null && !matches.isEmpty()) reportSpeech(matches);
                }
                @Override public void onError(int error) {
                    recognizerActive = false;
                    reportLevel(0f);
                    if (error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT) {
                        // Se teve som alto e mesmo assim não veio texto, avisa (2 vezes seguidas)
                        if (peakRms > 6f && ++silentMisses >= 2) {
                            silentMisses = 0;
                            reportVoiceStatus("Ouvi som mas não peguei as palavras. Chega mais perto do microfone.");
                        }
                        scheduleRestart(150);
                        return;
                    }
                    if (error == SpeechRecognizer.ERROR_RECOGNIZER_BUSY || error == SpeechRecognizer.ERROR_CLIENT) {
                        try { speechRecognizer.cancel(); } catch (RuntimeException ignored) { }
                        scheduleRestart(400);
                        return;
                    }
                    if (error == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS) {
                        reportVoiceError(voiceErrorMessage(error));
                        voiceListening = false;
                        return;
                    }
                    reportVoiceStatus(voiceErrorMessage(error) + " (erro " + error + ")");
                    if (error == SpeechRecognizer.ERROR_AUDIO || error == SpeechRecognizer.ERROR_SERVER) {
                        // Às vezes o serviço trava: recria o reconhecedor
                        try { speechRecognizer.destroy(); } catch (RuntimeException ignored) { }
                        speechRecognizer = null;
                        mainHandler.postDelayed(() -> startVoiceCapture(), 1200);
                        return;
                    }
                    scheduleRestart(error == SpeechRecognizer.ERROR_NETWORK || error == SpeechRecognizer.ERROR_NETWORK_TIMEOUT ? 2000 : 800);
                }
            });
        }
        beginRecognition();
    }

    private SpeechRecognizer createBestRecognizer() {
        // Prefere o serviço do Google: o serviço padrão de alguns aparelhos (Xiaomi etc.) não devolve texto para outros apps
        String[][] candidates = {
            {"com.google.android.googlequicksearchbox", "com.google.android.voicesearch.serviceapi.GoogleRecognitionService", "Google"},
            {"com.google.android.tts", "com.google.android.apps.speech.tts.googletts.service.GoogleTTSRecognitionService", "Google Speech"},
        };
        try {
            List<ResolveInfo> services = getPackageManager().queryIntentServices(new Intent("android.speech.RecognitionService"), 0);
            for (String[] c : candidates) {
                for (ResolveInfo info : services) {
                    if (info.serviceInfo != null && c[0].equals(info.serviceInfo.packageName)) {
                        recognizerName = c[2];
                        return SpeechRecognizer.createSpeechRecognizer(this, new ComponentName(info.serviceInfo.packageName, info.serviceInfo.name));
                    }
                }
            }
        } catch (RuntimeException ignored) { }
        recognizerName = "padrão do aparelho";
        return SpeechRecognizer.createSpeechRecognizer(this);
    }

    private void reportLevel(float level) {
        if (webView == null) return;
        String call = "window.onNativeVoiceLevel && window.onNativeVoiceLevel(" + level + ");";
        webView.post(() -> webView.evaluateJavascript(call, null));
    }

    private void scheduleRestart(long delayMs) {
        mainHandler.removeCallbacksAndMessages(null);
        if (voiceListening && activityVisible) mainHandler.postDelayed(() -> beginRecognition(), delayMs);
    }

    private void beginRecognition() {
        if (!voiceListening || !activityVisible || speechRecognizer == null || recognizerActive) return;
        Intent intent = new Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM);
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE, "pt-BR");
        intent.putExtra(RecognizerIntent.EXTRA_LANGUAGE_PREFERENCE, "pt-BR");
        intent.putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, true);
        intent.putExtra(RecognizerIntent.EXTRA_ONLY_RETURN_LANGUAGE_PREFERENCE, true);
        intent.putExtra(RecognizerIntent.EXTRA_CALLING_PACKAGE, getPackageName());
        // Vários palpites: o painel escolhe o que faz sentido como comando
        intent.putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 5);
        // Espera mais silêncio antes de encerrar, para dar tempo de falar com calma
        intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS, 2500L);
        intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_POSSIBLY_COMPLETE_SILENCE_LENGTH_MILLIS, 2000L);
        intent.putExtra(RecognizerIntent.EXTRA_SPEECH_INPUT_MINIMUM_LENGTH_MILLIS, 1500L);
        final SpeechRecognizer current = speechRecognizer;
        watchdogHandler.removeCallbacksAndMessages(null);
        watchdogHandler.postDelayed(() -> {
            if (voiceListening && !readyOnce && speechRecognizer == current)
                reportVoiceStatus("O microfone não iniciou (" + recognizerName + "). Feche apps que usam o microfone, como gravador de tela.");
        }, 6000);
        try { speechRecognizer.startListening(intent); recognizerActive = true; }
        catch (RuntimeException error) { recognizerActive = false; mainHandler.postDelayed(() -> beginRecognition(), 1000); }
    }

    private void reportSpeech(ArrayList<String> matches) {
        if (webView == null) return;
        JSONArray all = new JSONArray();
        for (String m : matches) if (m != null && m.trim().length() > 0) all.put(m);
        if (all.length() == 0) return;
        String call = "window.onNativeSpeechResult && window.onNativeSpeechResult(" + JSONObject.quote(matches.get(0)) + "," + all.toString() + ");";
        webView.post(() -> webView.evaluateJavascript(call, null));
    }

    private void reportVoiceError(String message) {
        if (webView == null) return;
        String call = "window.onNativeVoiceError && window.onNativeVoiceError(" + JSONObject.quote(message) + ");";
        webView.post(() -> webView.evaluateJavascript(call, null));
    }

    private void reportSpeakDone() {
        if (webView == null) return;
        webView.post(() -> webView.evaluateJavascript("window.onNativeSpeakDone && window.onNativeSpeakDone();", null));
    }

    private void reportVoiceStatus(String message) {
        if (webView == null) return;
        String call = "window.onNativeSpeechStatus && window.onNativeSpeechStatus(" + JSONObject.quote(message) + ");";
        webView.post(() -> webView.evaluateJavascript(call, null));
    }

    private String voiceErrorMessage(int error) {
        if (error == SpeechRecognizer.ERROR_INSUFFICIENT_PERMISSIONS) return "O Android não liberou o microfone para o Tela Tablet.";
        if (error == SpeechRecognizer.ERROR_NETWORK || error == SpeechRecognizer.ERROR_NETWORK_TIMEOUT) return "O reconhecimento de voz precisa de internet. Confira a conexão do tablet.";
        if (error == SpeechRecognizer.ERROR_LANGUAGE_UNAVAILABLE) return "O serviço de voz do tablet não tem Português (Brasil) disponível.";
        if (error == SpeechRecognizer.ERROR_NO_MATCH || error == SpeechRecognizer.ERROR_SPEECH_TIMEOUT) return "Não entendi a fala. Tente dizer ‘adiciona café à lista’ mais perto do microfone.";
        if (error == SpeechRecognizer.ERROR_AUDIO) return "O Android teve um problema ao captar o áudio do microfone.";
        return "O serviço de voz não retornou a fala. Verifique o app de reconhecimento de voz do tablet.";
    }

    private void stopVoiceCapture() {
        voiceListening = false;
        recognizerActive = false;
        mainHandler.removeCallbacksAndMessages(null);
        watchdogHandler.removeCallbacksAndMessages(null);
        if (speechRecognizer != null) {
            try { speechRecognizer.cancel(); } catch (RuntimeException ignored) { }
        }
    }

    @Override public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == RECORD_AUDIO_REQUEST) {
            pendingVoicePermission = false;
            if (grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED) startVoiceCapture();
            else reportVoiceError("Permita o microfone para usar o assistente de voz.");
        }
    }

    @Override protected void onPause() {
        activityVisible = false;
        if (!pendingVoicePermission) stopVoiceCapture();
        super.onPause();
    }

    @Override protected void onResume() {
        super.onResume();
        activityVisible = true;
    }

    @Override protected void onDestroy() {
        stopVoiceCapture();
        if (speechRecognizer != null) { speechRecognizer.destroy(); speechRecognizer = null; }
        if (tts != null) { tts.shutdown(); tts = null; }
        super.onDestroy();
    }

    @Override protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == PICK_MEDIA && uploadCallback != null) {
            android.net.Uri[] result = resultCode == Activity.RESULT_OK && data != null && data.getData() != null
                ? new android.net.Uri[]{data.getData()} : null;
            uploadCallback.onReceiveValue(result); uploadCallback = null;
        }
    }

    @Override public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else showConnectionScreen();
    }
}
