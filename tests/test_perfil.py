"""Perfil sincronizado (2.13): montar/aplicar, arquivo, perfis da empresa, clientes compartilhados, sincronizador."""

import json

import pytest

from core import sincronia as S


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGENDAS_HOME", str(tmp_path / "home"))
    return tmp_path


def _db(path):
    from app.db import Database
    return Database(path)


def test_montar_e_aplicar_em_outro_computador(home):
    from app import perfil as P
    from core.config import Settings
    a = _db(home / "a.db")
    s = Settings.load()
    s.translator_name, s.projects_root, s.use_gpu, s.translate_method = "Ana Lima", "C:/Trabalhos", "nao", "api"
    s.save()
    pid = a.save_project({"name": "Globo", "context": "novela", "target_lang": "es-419",
                          "glossary": [{"term": "Oi", "translation": "Hola", "note": ""}]})
    a.save_profile("proprio-1", {"name": "Meu perfil", "max_chars_per_line": 40})
    snap = P.montar(a)
    assert snap["settings"]["translator_name"] == "Ana Lima"
    assert "projects_root" not in snap["settings"] and "use_gpu" not in snap["settings"], "o que é deste computador fica"
    assert any(c["name"] == "Globo" and c["glossario"][0]["translation"] == "Hola" for c in snap["clientes"])
    assert "proprio-1" in snap["perfis"]
    assert pid
    # "outro computador": configurações zeradas, outro banco
    s2 = Settings.load(); s2.translator_name = ""; s2.projects_root = "D:/Outro"; s2.translate_method = "chat"; s2.save()
    b = _db(home / "b.db")
    r = P.aplicar(b, json.loads(json.dumps(snap)))
    assert r["clientes_novos"] >= 1 and r["perfis"] == 1
    s3 = Settings.load()
    assert s3.translator_name == "Ana Lima" and s3.translate_method == "api" and s3.projects_root == "D:/Outro"
    g = [p for p in b.list_projects() if p["name"] == "Globo"][0]
    assert b.get_project(g["id"])["glossary"][0]["term"] == "Oi"
    # aplicar de novo não duplica
    r2 = P.aplicar(b, snap)
    assert r2["clientes_novos"] == 0 and r2["clientes_atualizados"] == 0
    assert len([p for p in b.list_projects() if p["name"].lower() == "globo"]) == 1


def test_arquivo_de_perfil():
    arq = S.para_arquivo({"v": 1, "clientes": []})
    assert S.de_arquivo(json.loads(json.dumps(arq))) == {"v": 1, "clientes": []}
    with pytest.raises(S.SincroniaError):
        S.de_arquivo({"perfis": {}})
    with pytest.raises(S.SincroniaError):
        S.de_arquivo({**arq, "versao": 99})


def test_perfis_da_empresa(home):
    from app import perfil as P
    db = _db(home / "a.db")
    ws = {"nome": "Estúdio X", "perfis": [{"id": 7, "nome": "Netflix", "padrao": True, "dados": {"max_chars_per_line": 39, "lixo": 1}}]}
    assert P.aplicar_perfis_empresa(db, ws) == 1
    p = [x for x in db.list_profiles() if x["key"] == "empresa-7"][0]
    assert p["name"] == "Estúdio X: Netflix" and p["max_chars_per_line"] == 39 and p["extra"]["padrao"] is True
    assert "empresa-7" not in P.montar(db)["perfis"], "perfil da empresa não entra no perfil do usuário"
    P.aplicar_perfis_empresa(db, {"nome": "Estúdio X", "perfis": []})
    assert not any(x["key"] == "empresa-7" for x in db.list_profiles()), "empresa parou de compartilhar: some"


class FakeServidor:
    """Imita /v1/sync com dois computadores."""

    def __init__(self):
        self.pool, self.perfil, self.outros, self.metricas_rec, self.enviados = {}, None, [], [], []
        self.ws = None

    def estado(self):
        return {"perfil": self.perfil, "outros": self.outros, "workspace": self.ws}

    def enviar(self, dados):
        self.enviados.append(dados)
        self.perfil = {"id": 1, "versao": len(self.enviados), "hash": "x"}
        return self.perfil

    def restaurar(self, pid):
        return {"versao": 1, "dados": {"v": 1, "settings": {"translator_name": "Restaurada"}, "clientes": [{"name": "SBT"}], "perfis": {}}}

    def workspace(self, clientes):
        for c in clientes:
            self.pool[c["chave"]] = c["dados"]
        return {"ativo": True, "glossarios": True, "clientes": [{"chave": k, "dados": v} for k, v in self.pool.items()]}

    def metricas(self, itens):
        self.metricas_rec.append(itens)
        return {"ok": True}


def test_clientes_compartilhados_entre_dois_computadores(home):
    from app import perfil as P
    srv = FakeServidor()
    a, b = _db(home / "a.db"), _db(home / "b.db")
    a.save_project({"name": "Globo", "context": "novela"})
    P.sincronizar_clientes_empresa(a, srv)
    r = P.sincronizar_clientes_empresa(b, srv)
    assert r["recebidos"] >= 1 and any(p["name"] == "Globo" for p in b.list_projects())
    # b muda; a recebe a mudança
    gid = [p for p in b.list_projects() if p["name"] == "Globo"][0]["id"]
    b.save_project({**b.get_project(gid), "context": "novela das nove"}, gid)
    P.sincronizar_clientes_empresa(b, srv)
    P.sincronizar_clientes_empresa(a, srv)
    ga = [p for p in a.list_projects() if p["name"] == "Globo"][0]
    assert a.get_project(ga["id"])["context"] == "novela das nove"
    # sem mudanças: nada enviado
    assert P.sincronizar_clientes_empresa(a, srv)["enviados"] == 0


def test_sincronizador_oferece_restaurar_e_depois_envia(home):
    from app import perfil as P
    srv = FakeServidor()
    srv.outros = [{"id": 5, "nome": "PC-ESPOSA", "atualizado_em": "2026-10-23T10:00:00Z"}]
    db = _db(home / "a.db")
    sync = P.Sincronizador(db, srv)
    st = sync.agora()
    assert st["sugerir_restaurar"] is True and srv.enviados == [], "não envia antes de ela decidir"
    resumo = sync.restaurar(5)
    assert resumo["clientes_novos"] == 1
    from core.config import Settings
    assert Settings.load().translator_name == "Restaurada"
    assert srv.enviados, "depois de restaurar, o perfil deste computador é enviado"
    n = len(srv.enviados)
    sync.agora()
    assert len(srv.enviados) == n, "sem mudança, não reenvia"
    db.save_project({"name": "Novo cliente"})
    sync.agora()
    assert len(srv.enviados) == n + 1


def test_sem_licenca_nao_sincroniza(home, monkeypatch):
    from app import perfil as P
    from core import licenca as L
    class Gratis:
        estado = L.Estado(modo="gratis")
        device = {"id": "0" * 64}
    L.definir(Gratis())
    sync = P.Sincronizador(_db(home / "a.db"), FakeServidor())
    assert sync.agora()["estado"] == "indisponivel"


def test_api_perfil_endpoints(server):  # noqa: F811
    from tests.test_app_server import call
    app, port, _ = server
    fake = FakeServidor()
    app.sincronia.cli = fake
    st = call(port, "GET", "/api/perfil", token=app.token)[1]
    assert st["disponivel"] is True and st["estado"] == "parado"
    r = call(port, "POST", "/api/perfil/sincronizar", token=app.token)[1]
    assert r["estado"] == "ok" and fake.enviados
    # salvar um cliente acorda a sincronização
    app.sincronia._acordar.clear()
    call(port, "POST", "/api/projects", {"name": "Cliente Z"}, token=app.token)
    assert app.sincronia._acordar.is_set()


from tests.test_app_server import server  # noqa: E402,F401
