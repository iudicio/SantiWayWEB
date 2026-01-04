# Скрипт для локального деплоя в minikube/kind
# Использование: .\deploy-local.ps1 [build|deploy|status|logs|clean]

param(
    [Parameter(Position=0)]
    [ValidateSet("build", "deploy", "status", "logs", "clean", "all")]
    [string]$Action = "all"
)

$NAMESPACE = "santiway"
$REGISTRY = "localhost:5000"  # Для kind с локальным registry

function Write-Step($msg) {
    Write-Host "`n=== $msg ===" -ForegroundColor Cyan
}

function Build-Images {
    Write-Step "Building Docker images"
    
    # Основной образ Django
    docker build -t "${REGISTRY}/santiway-web:latest" -f Dockerfile .
    
    # CHWriter
    docker build -t "${REGISTRY}/chwriter:latest" -f microservices/CHWriter/Dockerfile microservices/CHWriter/
    
    Write-Host "Images built successfully" -ForegroundColor Green
}

function Push-ToKind {
    Write-Step "Loading images to kind cluster"
    
    # Для kind нужно загружать образы напрямую в кластер
    kind load docker-image "${REGISTRY}/santiway-web:latest"
    kind load docker-image "${REGISTRY}/chwriter:latest"
    
    Write-Host "Images loaded to kind" -ForegroundColor Green
}

function Deploy-All {
    Write-Step "Deploying to Kubernetes"
    
    # Применяем через kustomize
    kubectl apply -k k8s/
    
    Write-Step "Waiting for pods to be ready..."
    kubectl wait --for=condition=ready pod -l project=santiway -n $NAMESPACE --timeout=300s 2>$null
    
    Write-Host "Deployment complete" -ForegroundColor Green
}

function Show-Status {
    Write-Step "Cluster Status"
    
    Write-Host "`nNamespace: $NAMESPACE" -ForegroundColor Yellow
    
    Write-Host "`n--- Pods ---" -ForegroundColor Yellow
    kubectl get pods -n $NAMESPACE -o wide
    
    Write-Host "`n--- Services ---" -ForegroundColor Yellow
    kubectl get svc -n $NAMESPACE
    
    Write-Host "`n--- PVC ---" -ForegroundColor Yellow
    kubectl get pvc -n $NAMESPACE
    
    Write-Host "`n--- Deployments ---" -ForegroundColor Yellow
    kubectl get deployments -n $NAMESPACE
    
    Write-Host "`n--- StatefulSets ---" -ForegroundColor Yellow
    kubectl get statefulsets -n $NAMESPACE
}

function Show-Logs {
    param([string]$PodName)
    
    if ($PodName) {
        kubectl logs -f -n $NAMESPACE $PodName
    } else {
        Write-Host "Available pods:" -ForegroundColor Yellow
        kubectl get pods -n $NAMESPACE -o name
        Write-Host "`nUsage: .\deploy-local.ps1 logs <pod-name>" -ForegroundColor Cyan
    }
}

function Clean-All {
    Write-Step "Cleaning up"
    
    kubectl delete -k k8s/ --ignore-not-found
    
    Write-Host "Cleanup complete" -ForegroundColor Green
}

# Main
switch ($Action) {
    "build" { Build-Images }
    "deploy" { Deploy-All }
    "status" { Show-Status }
    "logs" { Show-Logs }
    "clean" { Clean-All }
    "all" {
        Build-Images
        Deploy-All
        Show-Status
    }
}

