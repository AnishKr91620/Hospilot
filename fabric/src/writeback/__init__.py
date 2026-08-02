"""Write-back to the DB — Fabric's approved changes leaving for the upstream HIS.

Only used when INTEGRATION_MODE=kafka, where proposals are PUSHED to
`hospilot.sync.write`. In change_api / polling mode the DB pulls them over HTTP
instead ($pending-changes in api/changes/) and nothing here starts.

Depends downward on messaging.* + fhirgw.* + service.change_store.
"""
