#!/bin/bash
# Every command is on one line (no backslash continuations) so pasting can't merge lines.

# --- Java 25 (the base image only has OpenJDK 21) ---
apt-get update -qq && apt-get install -y -qq openjdk-25-jdk-headless || exit 1
update-alternatives --set java /usr/lib/jvm/java-25-openjdk-amd64/bin/java || true
java -version

# --- sbt: prefer the Google Maven Central mirror, fall back to Maven Central ---
mkdir -p "$HOME/.sbt" "$HOME/.config/sbt"
REPOS="$HOME/.sbt/repositories"
echo '[repositories]' > "$REPOS"
echo '  local' >> "$REPOS"
echo '  google-maven-central: https://maven-central.storage-download.googleapis.com/maven2/' >> "$REPOS"
echo '  maven-central' >> "$REPOS"
echo '-Dsbt.override.build.repos=true' > "$HOME/.config/sbt/sbtopts"
echo "--- $REPOS:"; cat "$REPOS"
[ "$(wc -l < "$REPOS")" -eq 4 ] || { echo "ERROR: unexpected $REPOS"; exit 1; }

# --- Pre-download sbt itself so sessions don't fetch it (cached with the environment) ---
SBT_VERSION=2.0.10
WARM="$(mktemp -d)"
mkdir -p "$WARM/project"
echo "sbt.version=$SBT_VERSION" > "$WARM/project/build.properties"
LAUNCH_PATH="org/scala-sbt/sbt-launch/$SBT_VERSION/sbt-launch-$SBT_VERSION.jar"
curl -fsSL -o "$WARM/sbt-launch.jar" "https://maven-central.storage-download.googleapis.com/maven2/$LAUNCH_PATH" || curl -fsSL -o "$WARM/sbt-launch.jar" "https://repo1.maven.org/maven2/$LAUNCH_PATH"
(cd "$WARM" && test -s sbt-launch.jar && timeout 240 java -Duser.home="$HOME" -Dsbt.repository.config="$REPOS" -Dsbt.override.build.repos=true -jar sbt-launch.jar about < /dev/null) || echo "sbt pre-download failed (non-fatal)"
rm -rf "$WARM"
ls "$HOME/.sbt/boot" || echo "WARNING: sbt was not pre-downloaded"

exit 0
