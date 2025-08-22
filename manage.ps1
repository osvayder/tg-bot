param([Parameter(Mandatory=$true)][ValidateSet('init-env','dev-up','dev-down','reset-db','logs','migrate','tests')][string]$cmd, [string]$service)

# Fix Docker Desktop PATH if not available
$dockerPath = 'C:\Program Files\Docker\Docker\resources\bin'
if (Test-Path $dockerPath) {
    $env:PATH = "$dockerPath;$env:PATH"
}

switch ($cmd) {

  'init-env' {
      Write-Host 'Predostavok ne trebuetsa - ubeditesj chto Docker Desktop uzhe ustanovlen.' -ForegroundColor Green
  }

  'dev-up' {
      docker compose up -d
  }

  'dev-down' {
      docker compose down
  }

  'reset-db' {
      docker compose down
      Remove-Item -Recurse -Force .\db-data  -ErrorAction SilentlyContinue
      docker compose up -d
  }
  
  'logs' {
      if ($service) {
          docker compose logs -f $service
      } else {
          docker compose logs -f
      }
  }
  
  'migrate' {
      Write-Host 'Running Django migrations...' -ForegroundColor Yellow
      docker exec -it tg-bot-admin-1 python manage.py migrate
  }
  
  'tests' {
      Write-Host 'Running tests...' -ForegroundColor Yellow
      docker exec -it tg-bot-admin-1 pytest tests/ -v
  }
}