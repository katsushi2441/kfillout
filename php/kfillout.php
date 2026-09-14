<?php
// Kurage 申請書記入アシスト (kfillout) — kurage.exbridge.jp 上の公開入口。自宅サーバー :18354 への透過プロキシ。
// UI は相対パスなので /kfillout.php/ (末尾スラッシュ) を起点に PATH_INFO で中継する。
// バックエンド URL は同ディレクトリの kfillout_config.php で定義（リポジトリには含めない）:
//   <?php define('KFILLOUT_BACKEND', 'http://あなたのサーバー:18354');
$__cfg = __DIR__ . '/kfillout_config.php';
if (is_file($__cfg)) { require_once $__cfg; }
$BACKEND = defined('KFILLOUT_BACKEND') ? KFILLOUT_BACKEND : 'http://127.0.0.1:18354';

if (!isset($_SERVER['PATH_INFO']) || $_SERVER['PATH_INFO'] === '') {
    if (substr($_SERVER['REQUEST_URI'], -1) !== '/' && strpos($_SERVER['REQUEST_URI'], '?') === false) {
        header('Location: /kfillout.php/', true, 302); exit;
    }
}
$path = isset($_SERVER['PATH_INFO']) ? $_SERVER['PATH_INFO'] : '/';
$qs = isset($_SERVER['QUERY_STRING']) && $_SERVER['QUERY_STRING'] !== '' ? '?' . $_SERVER['QUERY_STRING'] : '';

$ch = curl_init($BACKEND . $path . $qs);
$headers = array('X-Forwarded-Proto: https', 'X-Forwarded-Host: kurage.exbridge.jp');
if (!empty($_SERVER['HTTP_X_FORWARDED_FOR'])) { $headers[] = 'X-Forwarded-For: ' . $_SERVER['HTTP_X_FORWARDED_FOR']; }
elseif (!empty($_SERVER['REMOTE_ADDR'])) { $headers[] = 'X-Forwarded-For: ' . $_SERVER['REMOTE_ADDR']; }
if (!empty($_SERVER['HTTP_USER_AGENT'])) { $headers[] = 'User-Agent: ' . $_SERVER['HTTP_USER_AGENT']; }
if (!empty($_SERVER['HTTP_COOKIE'])) { $headers[] = 'Cookie: ' . $_SERVER['HTTP_COOKIE']; }
if (!empty($_SERVER['CONTENT_TYPE'])) { $headers[] = 'Content-Type: ' . $_SERVER['CONTENT_TYPE']; }
curl_setopt_array($ch, array(
    CURLOPT_CUSTOMREQUEST => $_SERVER['REQUEST_METHOD'],
    CURLOPT_RETURNTRANSFER => true, CURLOPT_HEADER => true,
    CURLOPT_HTTPHEADER => $headers, CURLOPT_ENCODING => '',
    // 様式の解析はローカルLLMを呼ぶので時間がかかる（5空欄で約10秒、多い様式はもっと）。
    // 旧形式は LibreOffice の往復も入るので、余裕を持って 300 秒にする。
    CURLOPT_TIMEOUT => 300, CURLOPT_FOLLOWLOCATION => false,
));
if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    // ファイルのアップロードがあるので multipart の本文をそのまま渡す。
    // file_get_contents('php://input') は PHP が multipart を解析済みだと空になるため、
    // 解析結果から組み直す（enable_post_data_reading=Off に頼らない）。
    $raw = file_get_contents('php://input');
    if ($raw === '' && (!empty($_POST) || !empty($_FILES))) {
        $b = '';
        $bd = '----kfillout' . bin2hex(random_bytes(8));
        foreach ($_POST as $k => $v) {
            foreach ((array)$v as $vv) {
                $b .= "--$bd\r\nContent-Disposition: form-data; name=\"$k\"\r\n\r\n$vv\r\n";
            }
        }
        foreach ($_FILES as $k => $f) {
            if (!is_uploaded_file($f['tmp_name'])) { continue; }
            $b .= "--$bd\r\nContent-Disposition: form-data; name=\"$k\"; filename=\"" . $f['name'] . "\"\r\n";
            $b .= 'Content-Type: ' . ($f['type'] ?: 'application/octet-stream') . "\r\n\r\n";
            $b .= file_get_contents($f['tmp_name']) . "\r\n";
        }
        $b .= "--$bd--\r\n";
        $raw = $b;
        foreach ($headers as $i => $h) {
            if (stripos($h, 'Content-Type:') === 0) { unset($headers[$i]); }
        }
        $headers[] = 'Content-Type: multipart/form-data; boundary=' . $bd;
        curl_setopt($ch, CURLOPT_HTTPHEADER, array_values($headers));
    }
    curl_setopt($ch, CURLOPT_POSTFIELDS, $raw);
}
$res = curl_exec($ch);
if ($res === false) { http_response_code(502); header('Content-Type: text/plain; charset=utf-8');
    echo 'Kurage 申請書記入アシストのバックエンドに接続できません'; exit; }
$status = curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
$hsize = curl_getinfo($ch, CURLINFO_HEADER_SIZE);
$ctype = (string)curl_getinfo($ch, CURLINFO_CONTENT_TYPE);
curl_close($ch);
http_response_code($status);
foreach (explode("\r\n", substr($res, 0, $hsize)) as $h) {
    if (stripos($h, 'Content-Type:') === 0 || stripos($h, 'Cache-Control:') === 0 || stripos($h, 'Set-Cookie:') === 0 || stripos($h, 'Content-Disposition:') === 0) { header($h, false); }
    if (stripos($h, 'Location:') === 0) { header('Location: ' . trim(substr($h, 9)), true, $status); }
}
$body = substr($res, $hsize);
if (stripos($ctype, 'text/html') !== false) {
    $tag = '<script>(function(){var s=document.createElement("script");s.src="https://kurage.exbridge.jp/simpletrack.php?url="+encodeURIComponent(location.href)+"&ref="+encodeURIComponent(document.referrer);document.head.appendChild(s)})();</script>';
    $body = str_replace('</head>', $tag . '</head>', $body);
}
echo $body;
