#!/bin/bash
# Build the signed APK and publish it for the control page's "Baixar app Android" button.
#   ANDROID_HOME=/path/to/sdk ./build.sh
# The signing key lives outside git: s3://<bucket>/app/release.keystore + SSM /agentepessoal/apk-keystore-password.
# The same key must sign every version, or Android refuses to update the installed app.
set -euo pipefail
cd "$(dirname "$0")"
: "${ANDROID_HOME:?set ANDROID_HOME to an Android SDK with platforms;android-35 and build-tools;35.0.0}"
REGION=us-east-1
ACCOUNT=$(aws sts get-caller-identity --query Account --output text)
BUCKET="agentepessoal-backup-${ACCOUNT}"
PARAM=/agentepessoal/apk-keystore-password
WORK=$(mktemp -d); trap 'rm -rf "$WORK"' EXIT
KS="$WORK/release.keystore"

if aws s3 cp "s3://${BUCKET}/app/release.keystore" "$KS" --region $REGION --only-show-errors 2>/dev/null; then
  PASS=$(aws ssm get-parameter --region $REGION --name $PARAM --with-decryption --query Parameter.Value --output text)
else
  echo "creating a new signing key (first build)"
  PASS=$(head -c 24 /dev/urandom | base64 | tr -dc A-Za-z0-9)
  keytool -genkeypair -keystore "$KS" -storepass "$PASS" -keypass "$PASS" -alias agente \
    -keyalg RSA -keysize 3072 -validity 10000 -dname "CN=Agente pessoal" >/dev/null 2>&1
  aws ssm put-parameter --region $REGION --name $PARAM --type SecureString --value "$PASS" --overwrite >/dev/null
  aws s3 cp "$KS" "s3://${BUCKET}/app/release.keystore" --region $REGION --only-show-errors
fi

export AGENTE_KEYSTORE="$KS" AGENTE_KEYSTORE_PASSWORD="$PASS"
echo "sdk.dir=${ANDROID_HOME}" > local.properties
gradle --quiet assembleRelease
APK=app/build/outputs/apk/release/app-release.apk
"$ANDROID_HOME"/build-tools/35.0.0/apksigner verify "$APK"
aws s3 cp "$APK" "s3://${BUCKET}/app/agente.apk" --region $REGION --only-show-errors \
  --content-type application/vnd.android.package-archive
echo "published s3://${BUCKET}/app/agente.apk ($(du -h "$APK" | cut -f1))"
