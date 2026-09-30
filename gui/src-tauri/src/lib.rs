//! LoreWriter desktop shell.
//!
//! The UI talks to the backend through the commands below (see `src/backend/` in the
//! frontend). They are stubs: wire them to the existing LoreWriter core — either by
//! porting the logic here or by spawning the TUI's Python core as a Tauri sidecar and
//! forwarding JSON. Until then the frontend falls back to its mock backend.

#[tauri::command]
fn get_workspace() -> Result<serde_json::Value, String> {
  Err("backend not connected".into())
}

#[tauri::command]
fn save_document(id: String, paragraphs: Vec<String>) -> Result<(), String> {
  let _ = (id, paragraphs);
  Err("backend not connected".into())
}

#[tauri::command]
fn ask_assistant(prompt: String, scope: String) -> Result<String, String> {
  let _ = (prompt, scope);
  Err("backend not connected".into())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
  tauri::Builder::default()
    .setup(|app| {
      if cfg!(debug_assertions) {
        app.handle().plugin(
          tauri_plugin_log::Builder::default()
            .level(log::LevelFilter::Info)
            .build(),
        )?;
      }
      Ok(())
    })
    .invoke_handler(tauri::generate_handler![get_workspace, save_document, ask_assistant])
    .run(tauri::generate_context!())
    .expect("error while building tauri application");
}
