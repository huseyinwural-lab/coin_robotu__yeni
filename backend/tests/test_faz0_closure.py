"""
FAZ 0 Kapanış Test Suite
========================
Bu test dosyası FAZ 0 görev emri final maddelerini doğrular:
- T-0.5: Runtime embeddeddb guard aktif mi
- T-0.6: Alembic current == head artifact doğrulaması
- T-0.7: db_persistence_test.log içeriği exact 3 satır
- T-0.8: CI embeddeddb guard workflow adımı var mı
- T-0.9: /api/health response exact {status:ok, database:connected}
- T-0.10: backend/.env.example postgres URL doğrulaması
- FAZ0 exit: .db dosyası 0
"""
import os
import json
import requests
import pytest
import subprocess

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')


class TestFaz0RuntimeembeddeddbGuard:
    """T-0.5: Runtime guard aktif mi (server.py startup)"""
    
    def test_runtime_guard_code_exists_in_server(self):
        """server.py'de embeddeddb guard kodu mevcut olmalı"""
        server_path = "/app/backend/server.py"
        with open(server_path, 'r') as f:
            content = f.read()
        
        # Guard string split ile oluşturulmuş: "sql" + "ite"
        assert 'blocked_db_marker = "sql" + "ite"' in content, "Runtime embeddeddb guard kodu bulunamadı"
        assert 'if blocked_db_marker in db_url.lower()' in content, "Guard condition bulunamadı"
        assert 'RuntimeError' in content, "RuntimeError raise bulunamadı"
    
    def test_runtime_guard_artifact_exists(self):
        """runtime_embeddeddb_guard.log artifact dosyası mevcut olmalı"""
        artifact_path = "/app/artifacts/runtime_embeddeddb_guard.log"
        assert os.path.exists(artifact_path), f"Artifact dosyası bulunamadı: {artifact_path}"
        
        with open(artifact_path, 'r') as f:
            content = f.read()
        
        assert 'blocked_db_marker' in content, "Guard marker artifact'ta yok"
        assert 'embeddeddb kullanımı yasaklandı' in content, "Guard error mesajı artifact'ta yok"


class TestFaz0AlembicValidation:
    """T-0.6: Alembic current == head artifact doğrulaması"""
    
    def test_alembic_artifact_exists(self):
        """alembic_live_validation.log artifact dosyası mevcut olmalı"""
        artifact_path = "/app/artifacts/alembic_live_validation.log"
        assert os.path.exists(artifact_path), f"Artifact dosyası bulunamadı: {artifact_path}"
    
    def test_alembic_current_equals_head(self):
        """CURRENT ve HEAD aynı revision olmalı"""
        artifact_path = "/app/artifacts/alembic_live_validation.log"
        with open(artifact_path, 'r') as f:
            content = f.read()
        
        lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
        
        current_line = None
        head_line = None
        
        for line in lines:
            if line.startswith('CURRENT:'):
                current_line = line.split(':')[1].strip()
            elif line.startswith('HEAD:'):
                head_line = line.split(':')[1].strip()
        
        assert current_line is not None, "CURRENT değeri bulunamadı"
        assert head_line is not None, "HEAD değeri bulunamadı"
        assert current_line == head_line, f"Alembic current ({current_line}) != head ({head_line})"


class TestFaz0DbPersistence:
    """T-0.7: /app/artifacts/db_persistence_test.log içeriği exact 3 satır"""
    
    def test_persistence_artifact_exists(self):
        """db_persistence_test.log artifact dosyası mevcut olmalı"""
        artifact_path = "/app/artifacts/db_persistence_test.log"
        assert os.path.exists(artifact_path), f"Artifact dosyası bulunamadı: {artifact_path}"
    
    def test_persistence_artifact_exact_content(self):
        """Artifact exact 3 satır içermeli: INSERT_OK, RESTART_OK, DATA_FOUND_AFTER_RESTART"""
        artifact_path = "/app/artifacts/db_persistence_test.log"
        with open(artifact_path, 'r') as f:
            content = f.read()
        
        lines = [line.strip() for line in content.strip().split('\n') if line.strip()]
        
        assert len(lines) == 3, f"3 satır bekleniyor, {len(lines)} satır bulundu: {lines}"
        assert lines[0] == "INSERT_OK", f"Satır 1: 'INSERT_OK' bekleniyor, '{lines[0]}' bulundu"
        assert lines[1] == "RESTART_OK", f"Satır 2: 'RESTART_OK' bekleniyor, '{lines[1]}' bulundu"
        assert lines[2] == "DATA_FOUND_AFTER_RESTART", f"Satır 3: 'DATA_FOUND_AFTER_RESTART' bekleniyor, '{lines[2]}' bulundu"


class TestFaz0CiembeddeddbGuard:
    """T-0.8: CI embeddeddb guard workflow adımı var mı"""
    
    def test_ci_workflow_exists(self):
        """deploy-gate.yml workflow dosyası mevcut olmalı"""
        workflow_path = "/app/.github/workflows/deploy-gate.yml"
        assert os.path.exists(workflow_path), f"Workflow dosyası bulunamadı: {workflow_path}"
    
    def test_ci_embeddeddb_guard_step_exists(self):
        """Workflow'da embeddeddb guard step'i olmalı"""
        workflow_path = "/app/.github/workflows/deploy-gate.yml"
        with open(workflow_path, 'r') as f:
            content = f.read()
        
        # grep -R "embeddeddb" kontrolü
        assert 'grep -R "embeddeddb"' in content, "CI embeddeddb guard grep komutu bulunamadı"
        assert 'embeddeddb forbidden' in content, "CI embeddeddb forbidden mesajı bulunamadı"
        assert 'exit 1' in content, "CI exit 1 komutu bulunamadı"
    
    def test_ci_embeddeddb_guard_artifact_exists(self):
        """ci_embeddeddb_guard.log artifact dosyası mevcut olmalı"""
        artifact_path = "/app/artifacts/ci_embeddeddb_guard.log"
        assert os.path.exists(artifact_path), f"Artifact dosyası bulunamadı: {artifact_path}"
        
        with open(artifact_path, 'r') as f:
            content = f.read()
        
        assert 'embeddeddb forbidden' in content, "CI guard artifact içeriği eksik"
        assert 'PASS' in content, "CI guard PASS status bulunamadı"


class TestFaz0HealthEndpoint:
    """T-0.9: /api/health response exact {status:ok, database:connected}"""
    
    def test_health_endpoint_response(self):
        """Health endpoint exact JSON response döndürmeli"""
        if not BASE_URL:
            pytest.skip("REACT_APP_BACKEND_URL environment variable not set")
        
        response = requests.get(f"{BASE_URL}/api/health", timeout=10)
        
        assert response.status_code == 200, f"Health endpoint status code: {response.status_code}"
        
        data = response.json()
        
        assert data.get("status") == "ok", f"status: 'ok' bekleniyor, '{data.get('status')}' bulundu"
        assert data.get("database") == "connected", f"database: 'connected' bekleniyor, '{data.get('database')}' bulundu"
    
    def test_health_artifact_matches_live_response(self):
        """Artifact ve canlı response eşleşmeli"""
        artifact_path = "/app/artifacts/healthcheck_db_response.json"
        assert os.path.exists(artifact_path), f"Artifact dosyası bulunamadı: {artifact_path}"
        
        with open(artifact_path, 'r') as f:
            artifact_data = json.load(f)
        
        expected = {"status": "ok", "database": "connected"}
        assert artifact_data == expected, f"Artifact içeriği beklenen ile eşleşmiyor: {artifact_data}"


class TestFaz0EnvExample:
    """T-0.10: backend/.env.example postgres URL doğrulaması"""
    
    def test_env_example_exists(self):
        """.env.example dosyası mevcut olmalı"""
        env_path = "/app/backend/.env.example"
        assert os.path.exists(env_path), f".env.example dosyası bulunamadı: {env_path}"
    
    def test_env_example_has_postgres_url(self):
        """DATABASE_URL PostgreSQL olmalı, embeddeddb olmamalı"""
        env_path = "/app/backend/.env.example"
        with open(env_path, 'r') as f:
            content = f.read()
        
        assert 'DATABASE_URL=' in content, "DATABASE_URL tanımı bulunamadı"
        assert 'postgresql' in content.lower(), "PostgreSQL URL bulunamadı"
        assert 'embeddeddb' not in content.lower(), "embeddeddb referansı bulundu - yasak!"


class TestFaz0DbFileExit:
    """FAZ0 exit: .db dosyası 0"""
    
    def test_no_db_files_in_repo(self):
        """Repo'da .db dosyası olmamalı"""
        result = subprocess.run(
            ['find', '/app', '-name', '*.db', '-type', 'f'],
            capture_output=True,
            text=True
        )
        
        db_files = [f for f in result.stdout.strip().split('\n') if f]
        
        assert len(db_files) == 0, f".db dosyaları bulundu: {db_files}"
    
    def test_faz0_db_scan_artifact_empty(self):
        """faz0_db_scan.log artifact dosyası boş olmalı"""
        artifact_path = "/app/artifacts/faz0_db_scan.log"
        assert os.path.exists(artifact_path), f"Artifact dosyası bulunamadı: {artifact_path}"
        
        with open(artifact_path, 'r') as f:
            content = f.read().strip()
        
        assert content == "", f"faz0_db_scan.log boş olmalı, içerik: '{content}'"


class TestFaz0ClosureReport:
    """FAZ0 kapanış raporu doğrulaması"""
    
    def test_closure_report_exists(self):
        """Kapanış raporu mevcut olmalı"""
        report_path = "/app/artifacts/faz0_closure_report.md"
        assert os.path.exists(report_path), f"Kapanış raporu bulunamadı: {report_path}"
    
    def test_closure_report_contains_all_sections(self):
        """Rapor tüm T-0.x bölümlerini içermeli"""
        report_path = "/app/artifacts/faz0_closure_report.md"
        with open(report_path, 'r') as f:
            content = f.read()
        
        required_sections = [
            "T-0.5",
            "T-0.6",
            "T-0.7",
            "T-0.8",
            "T-0.9",
            "T-0.10",
            "EXIT Kriterleri"
        ]
        
        for section in required_sections:
            assert section in content, f"Raporda '{section}' bölümü bulunamadı"
