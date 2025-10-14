{{- define "santiway.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "santiway.fullname" -}}
{{- $name := include "santiway.name" . -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s" $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "santiway.labels" -}}
app.kubernetes.io/name: {{ include "santiway.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion }}
app.kubernetes.io/managed-by: Helm
{{- end -}}

{{/* helper: гарантировать, что секрет не перегенерится на upgrade */}}
{{- define "santiway.existingOrRandomPass" -}}
{{- $ns := .ns -}}
{{- $name := .name -}}
{{- $key := .key -}}
{{- $provided := .provided -}}
{{- if $provided }}
{{- $provided -}}
{{- else -}}
{{- $secret := (lookup "v1" "Secret" $ns $name) -}}
{{- if $secret -}}
{{- index $secret.data $key | b64dec -}}
{{- else -}}
{{- randAlphaNum 24 -}}
{{- end -}}
{{- end -}}
{{- end -}}
