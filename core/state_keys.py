# Session state keys — single source of truth
SHEETS = "sheets"           # dict[str, pd.DataFrame] — parsed file data
RAW_BYTES = "raw_bytes"     # bytes — original file bytes for re-download
STAGE = "stage"             # str — current step in the flow
FILE_NAME = "file_name"     # str — original uploaded file name

# Stage values
STAGE_UPLOADED = "uploaded"
STAGE_COLUMNS = "columns_selected"
STAGE_MASKED = "masked"

# Phase 2 keys
SELECTED_COLUMNS = "selected_columns"  # dict[sheet_name, dict[col_name, bool]]
MASK_CONFIG = "mask_config"            # dict[sheet_name, dict[col_name, "text"|"numeric"]]
MAPPING = "mapping"                    # dict: {"text": {norm_val: pseudonym}, "numeric": {col: multiplier}}
MASKED_SHEETS = "masked_sheets"        # dict[str, pd.DataFrame]
STATS = "stats"                        # dict: {"masked_values": int, "unique_entities": int}

# Phase 3 keys — decryption page
DECR_SHEETS = "decr_sheets"      # dict[str, pd.DataFrame] — uploaded masked file
DECR_MAPPING = "decr_mapping"    # dict — loaded JSON mapping
DECR_RESULT = "decr_result"      # dict[str, pd.DataFrame] — decrypted sheets
