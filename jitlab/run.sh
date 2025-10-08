#!/bin/bash
set -e

mvn clean package -DskipTests


JAR_FILE="target/jitlab-0.0.1-SNAPSHOT.jar"

if [ ! -f "$JAR_FILE" ]; then
  exit 1
fi

java -jar "$JAR_FILE"
