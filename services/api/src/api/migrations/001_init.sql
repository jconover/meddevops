CREATE TABLE devices (
    id text PRIMARY KEY,
    model text NOT NULL,
    first_seen timestamptz NOT NULL,
    last_seen timestamptz NOT NULL
);

CREATE TABLE procedures (
    id uuid PRIMARY KEY,
    device_id text NOT NULL REFERENCES devices (id),
    procedure_type text NOT NULL,
    started_at timestamptz NOT NULL,
    ended_at timestamptz NOT NULL,
    status text NOT NULL
);

CREATE INDEX procedures_device_started_idx ON procedures (device_id, started_at DESC);

CREATE TABLE events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    procedure_id uuid NOT NULL REFERENCES procedures (id),
    ts timestamptz NOT NULL,
    event_type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'
);

CREATE INDEX events_procedure_id_idx ON events (procedure_id, id);

CREATE TABLE ingest_files (
    s3_key text PRIMARY KEY,
    status text NOT NULL CHECK (status IN ('processed', 'quarantined')),
    event_count integer,
    error text,
    received_at timestamptz NOT NULL,
    processed_at timestamptz NOT NULL DEFAULT now()
);
