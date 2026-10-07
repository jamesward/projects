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

# --- Gradle: prefer the Google Maven Central mirror (init script); the build's repositories stay as fallbacks ---
mkdir -p "$HOME/.gradle/init.d"
printf '%s\n' '// Cloud environment only: prefer the Google Maven Central mirror; the build'"'"'s own repositories stay as fallbacks.' 'val googleMirror = "https://maven-central.storage-download.googleapis.com/maven2/"' 'fun RepositoryHandler.preferGoogleMirror() {' '    if (any { it.name == "GoogleMavenCentralMirror" }) return' '    val repo = maven { name = "GoogleMavenCentralMirror"; url = uri(googleMirror) }' '    remove(repo)' '    addFirst(repo)' '}' 'beforeSettings {' '    pluginManagement.repositories.preferGoogleMirror()' '    pluginManagement.repositories.gradlePluginPortal()' '}' 'settingsEvaluated {' '    if (dependencyResolutionManagement.repositories.isNotEmpty()) dependencyResolutionManagement.repositories.preferGoogleMirror()' '}' 'allprojects {' '    afterEvaluate {' '        if (repositories.isNotEmpty()) repositories.preferGoogleMirror()' '        if (buildscript.repositories.isNotEmpty()) buildscript.repositories.preferGoogleMirror()' '    }' '}' > "$HOME/.gradle/init.d/google-maven-central.init.gradle.kts"
grep -q GoogleMavenCentralMirror "$HOME/.gradle/init.d/google-maven-central.init.gradle.kts" || { echo "ERROR: Gradle init script"; exit 1; }

# --- Maven: prefer the Google Maven Central mirror (active profile); Maven Central stays the fallback ---
mkdir -p "$HOME/.m2"
printf '%s\n' '<settings>' '  <!-- Cloud environment only: prefer the Google Maven Central mirror; Maven Central stays the fallback. -->' '  <profiles>' '    <profile>' '      <id>google-maven-central</id>' '      <repositories>' '        <repository><id>google-maven-central</id><url>https://maven-central.storage-download.googleapis.com/maven2/</url><snapshots><enabled>false</enabled></snapshots></repository>' '      </repositories>' '      <pluginRepositories>' '        <pluginRepository><id>google-maven-central</id><url>https://maven-central.storage-download.googleapis.com/maven2/</url><snapshots><enabled>false</enabled></snapshots></pluginRepository>' '      </pluginRepositories>' '    </profile>' '  </profiles>' '  <activeProfiles><activeProfile>google-maven-central</activeProfile></activeProfiles>' '</settings>' > "$HOME/.m2/settings.xml"
grep -q google-maven-central "$HOME/.m2/settings.xml" || { echo "ERROR: Maven settings"; exit 1; }

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
