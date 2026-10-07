# Android 14 (arm64) + MindTheGapps (Google Play Store and Play Services).
FROM redroid/redroid:14.0.0_64only-latest
COPY mindthegapps /
ENTRYPOINT ["/init", "androidboot.hardware=redroid", "ro.setupwizard.mode=DISABLED"]
