"""Backups use the native format and preserve the live MCP recovery channel."""

from tests.test_mcp_anki import native


def test_native_compatible_backup_restore_can_itself_be_undone_after_restart(tmp_path):
    native(
        tmp_path,
        """
        from backend.restore_bundle import precheck_backup
        settings_store={'mcp_enabled':True,'mcp_allow_writes':True}
        def save_settings(value):settings_store.clear();settings_store.update(value)
        def service():return McpService(str(root),'A','context',config=dict(settings_store),alive=lambda:True,save_config=save_settings)
        svc=service()
        note,cid=seed('Original before backup')
        path=root/'full.zip'
        def apply(action,**parameters):
            p=call('preview_operation',action=action,parameters=parameters)
            return call('apply_advanced_plan',plan_id=p['plan_id'])
        exported=apply('backup_export',path=str(path))
        assert precheck_backup(path,target_profile='A').card_count==1
        note['Front']='After backup';col.update_note(note)
        restored=apply('backup_restore',path=str(path))
        assert col.get_note(note.id)['Front']=='Original before backup'
        assert settings_store['mcp_enabled'] and settings_store['mcp_allow_writes']
        restart();call('undo_change',undo_id=restored['undo_id'])
        assert col.get_note(note.id)['Front']=='After backup'
        assert call('get_undo_history')['items']
        call('undo_change',undo_id=exported['undo_id'])
        assert not path.exists()
    """,
    )
