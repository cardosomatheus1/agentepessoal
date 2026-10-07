package com.agentepessoal.app;

import android.Manifest;
import android.app.Activity;
import android.app.AlertDialog;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ClipboardManager;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.text.InputType;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.PermissionRequest;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.TextView;
import android.widget.Toast;

/**
 * Wraps the personal control page (start / hibernate the VM) and the Agent Zero UI it opens.
 *
 * The personal link (with its #k= key) is typed once and kept only in this app's private
 * storage, so the APK itself carries no access and can be reinstalled or shared safely.
 */
public class MainActivity extends Activity {
    private static final String PREFS = "agente";
    private static final String KEY_LINK = "link";
    private static final int REQ_FILES = 1;
    private static final int REQ_MIC = 2;

    private WebView web;
    private ValueCallback<Uri[]> filesCallback;
    private PermissionRequest pendingPermission;
    private long lastBack;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        String link = prefs().getString(KEY_LINK, "");
        if (link.isEmpty()) {
            showSetup();
        } else {
            showWeb(link, state);
        }
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    // ------------------------------------------------------------------ first run

    private void showSetup() {
        web = null;
        int pad = dp(24);
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setGravity(Gravity.CENTER_VERTICAL);
        box.setPadding(pad, pad, pad, pad);
        box.setBackgroundColor(Color.parseColor("#0D0D0D"));

        TextView title = new TextView(this);
        title.setText("Agente");
        title.setTextColor(Color.WHITE);
        title.setTextSize(28);
        box.addView(title);

        TextView hint = new TextView(this);
        hint.setText("Cole o seu link pessoal (o da página de controle, que termina com #k=…). Ele fica guardado só neste celular.");
        hint.setTextColor(Color.parseColor("#9A9A9A"));
        hint.setTextSize(15);
        hint.setPadding(0, dp(8), 0, dp(20));
        box.addView(hint);

        EditText field = new EditText(this);
        field.setHint("https://…lambda-url…/#k=…");
        field.setHintTextColor(Color.parseColor("#666666"));
        field.setTextColor(Color.WHITE);
        field.setSingleLine(true);
        field.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_URI);
        box.addView(field, new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        Button paste = new Button(this);
        paste.setText("Colar");
        paste.setOnClickListener(v -> {
            ClipboardManager cb = (ClipboardManager) getSystemService(Context.CLIPBOARD_SERVICE);
            if (cb != null && cb.hasPrimaryClip() && cb.getPrimaryClip().getItemCount() > 0) {
                CharSequence text = cb.getPrimaryClip().getItemAt(0).coerceToText(this);
                if (text != null) field.setText(text.toString().trim());
            }
        });
        box.addView(paste);

        Button save = new Button(this);
        save.setText("Entrar");
        save.setOnClickListener(v -> {
            String link = field.getText().toString().trim();
            if (!link.startsWith("https://") || !link.contains("#k=")) {
                Toast.makeText(this, "Esse não parece o link pessoal (precisa começar com https:// e ter #k=).", Toast.LENGTH_LONG).show();
                return;
            }
            prefs().edit().putString(KEY_LINK, link).apply();
            showWeb(link, null);
        });
        box.addView(save);

        setContentView(box);
    }

    // ------------------------------------------------------------------ web app

    private void showWeb(String link, Bundle state) {
        web = new WebView(this);
        web.setBackgroundColor(Color.parseColor("#0D0D0D"));
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setSupportMultipleWindows(false); // target=_blank links ("Ver celular") open in place
        s.setUserAgentString(s.getUserAgentString() + " AgenteApp/1.0");
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web, true);

        web.setWebViewClient(new WebViewClient() {
            @Override
            public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                String scheme = uri.getScheme() == null ? "" : uri.getScheme();
                if (scheme.equals("https") || scheme.equals("http")) return false;
                try { // mailto:, tel:, whatsapp:, intent: … go to the right app
                    startActivity(new Intent(Intent.ACTION_VIEW, uri));
                } catch (ActivityNotFoundException ignored) {
                }
                return true;
            }
        });

        web.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (filesCallback != null) filesCallback.onReceiveValue(null);
                filesCallback = callback;
                Intent pick = new Intent(Intent.ACTION_GET_CONTENT);
                pick.addCategory(Intent.CATEGORY_OPENABLE);
                pick.setType("*/*");
                if (params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE) {
                    pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
                }
                try {
                    startActivityForResult(Intent.createChooser(pick, "Escolher arquivos"), REQ_FILES);
                } catch (ActivityNotFoundException e) {
                    filesCallback = null;
                    return false;
                }
                return true;
            }

            @Override
            public void onPermissionRequest(PermissionRequest request) {
                // The agent's microphone button (speech to text).
                for (String r : request.getResources()) {
                    if (PermissionRequest.RESOURCE_AUDIO_CAPTURE.equals(r)) {
                        if (checkSelfPermission(Manifest.permission.RECORD_AUDIO) == PackageManager.PERMISSION_GRANTED) {
                            request.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
                        } else {
                            pendingPermission = request;
                            requestPermissions(new String[]{Manifest.permission.RECORD_AUDIO}, REQ_MIC);
                        }
                        return;
                    }
                }
                request.deny();
            }
        });

        web.setDownloadListener((url, userAgent, contentDisposition, mimeType, length) -> {
            if (!url.startsWith("http")) {
                Toast.makeText(this, "Esse download não é suportado no app; abra no navegador.", Toast.LENGTH_LONG).show();
                return;
            }
            String name = URLUtil.guessFileName(url, contentDisposition, mimeType);
            DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
            req.addRequestHeader("Cookie", CookieManager.getInstance().getCookie(url));
            req.addRequestHeader("User-Agent", userAgent);
            req.setMimeType(mimeType);
            req.setTitle(name);
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            if (dm != null) {
                dm.enqueue(req);
                Toast.makeText(this, "Baixando " + name, Toast.LENGTH_SHORT).show();
            }
        });

        setContentView(web);
        if (state == null || web.restoreState(state) == null) {
            web.loadUrl(link);
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        if (requestCode != REQ_FILES || filesCallback == null) {
            super.onActivityResult(requestCode, resultCode, data);
            return;
        }
        Uri[] result = null;
        if (resultCode == RESULT_OK && data != null) {
            if (data.getClipData() != null) {
                int n = data.getClipData().getItemCount();
                result = new Uri[n];
                for (int i = 0; i < n; i++) result[i] = data.getClipData().getItemAt(i).getUri();
            } else if (data.getData() != null) {
                result = new Uri[]{data.getData()};
            }
        }
        filesCallback.onReceiveValue(result);
        filesCallback = null;
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        if (requestCode == REQ_MIC && pendingPermission != null) {
            if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
                pendingPermission.grant(new String[]{PermissionRequest.RESOURCE_AUDIO_CAPTURE});
            } else {
                pendingPermission.deny();
            }
            pendingPermission = null;
        }
    }

    @Override
    public void onBackPressed() {
        if (web == null) {
            super.onBackPressed();
            return;
        }
        if (web.canGoBack()) {
            web.goBack();
            return;
        }
        long now = System.currentTimeMillis();
        if (now - lastBack < 2000) {
            new AlertDialog.Builder(this)
                    .setTitle("Agente")
                    .setItems(new CharSequence[]{"Sair", "Recarregar", "Trocar o link pessoal"}, (d, which) -> {
                        if (which == 0) finish();
                        else if (which == 1) web.reload();
                        else {
                            prefs().edit().remove(KEY_LINK).apply();
                            web.clearHistory();
                            showSetup();
                        }
                    })
                    .show();
        } else {
            lastBack = now;
            Toast.makeText(this, "Aperte voltar de novo para as opções", Toast.LENGTH_SHORT).show();
        }
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        if (web != null) web.saveState(out);
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
