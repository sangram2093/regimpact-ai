-- RegImpact GoogleSQL schema revision 001. NOT APPLIED / NOT CLOUD VALIDATED.
-- Requires an existing authorized Spanner Enterprise/Enterprise Plus or eligible trial.
-- This file creates tables/index/graph only; it does not create projects or instances.

CREATE TABLE RegulatoryInstrument (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE RegulationVersion (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE ChangeProposal (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE RegulatoryProvision (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE Mandate (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE Evidence (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE ProposedChangeStatement (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE ChangeItem (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE PolicyRequirement (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE ControlObjective (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE RiskType (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE RiskDriver (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE ImpactScenario (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL
) PRIMARY KEY (BundleId, Id);

CREATE TABLE MandateAddressedBy (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  SourceId STRING(128) NOT NULL,
  TargetId STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL,
  FOREIGN KEY (BundleId, SourceId) REFERENCES Mandate (BundleId, Id),
  FOREIGN KEY (BundleId, TargetId) REFERENCES PolicyRequirement (BundleId, Id)
) PRIMARY KEY (BundleId, Id);

CREATE INDEX MandateAddressedByBySource ON MandateAddressedBy (BundleId, SourceId, Status);

CREATE TABLE PolicyImplementedBy (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  SourceId STRING(128) NOT NULL,
  TargetId STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL,
  FOREIGN KEY (BundleId, SourceId) REFERENCES PolicyRequirement (BundleId, Id),
  FOREIGN KEY (BundleId, TargetId) REFERENCES ControlObjective (BundleId, Id)
) PRIMARY KEY (BundleId, Id);

CREATE INDEX PolicyImplementedByBySource ON PolicyImplementedBy (BundleId, SourceId, Status);

CREATE TABLE MandateClassifiedAs (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  SourceId STRING(128) NOT NULL,
  TargetId STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL,
  FOREIGN KEY (BundleId, SourceId) REFERENCES Mandate (BundleId, Id),
  FOREIGN KEY (BundleId, TargetId) REFERENCES RiskType (BundleId, Id)
) PRIMARY KEY (BundleId, Id);

CREATE INDEX MandateClassifiedAsBySource ON MandateClassifiedAs (BundleId, SourceId, Status);

CREATE TABLE MandateDrivenBy (
  BundleId STRING(128) NOT NULL,
  Id STRING(128) NOT NULL,
  SourceId STRING(128) NOT NULL,
  TargetId STRING(128) NOT NULL,
  Status STRING(32) NOT NULL,
  Payload JSON NOT NULL,
  FOREIGN KEY (BundleId, SourceId) REFERENCES Mandate (BundleId, Id),
  FOREIGN KEY (BundleId, TargetId) REFERENCES RiskDriver (BundleId, Id)
) PRIMARY KEY (BundleId, Id);

CREATE INDEX MandateDrivenByBySource ON MandateDrivenBy (BundleId, SourceId, Status);

CREATE TABLE SearchEntity (
  BundleId STRING(128) NOT NULL,
  EntityId STRING(128) NOT NULL,
  Kind STRING(32) NOT NULL,
  Status STRING(32) NOT NULL,
  SearchText STRING(MAX) NOT NULL,
  Embedding ARRAY<FLOAT32>(vector_length=>768),
  EmbeddingModel STRING(128),
  SearchTokens TOKENLIST AS (TOKENIZE_FULLTEXT(SearchText)) HIDDEN
) PRIMARY KEY (BundleId, EntityId);

CREATE SEARCH INDEX SearchEntityFullText ON SearchEntity (SearchTokens)
  STORING (Kind, Status, SearchText)
  PARTITION BY BundleId;

CREATE TABLE DemoSessions (
  SessionId STRING(36) NOT NULL,
  StateJson JSON NOT NULL,
  TouchedAt TIMESTAMP NOT NULL
) PRIMARY KEY (SessionId);

CREATE INDEX DemoSessionsByTouchedAt ON DemoSessions (TouchedAt);

CREATE PROPERTY GRAPH RegImpactGraph
NODE TABLES (
  Mandate LABEL Mandate PROPERTIES (BundleId, Id, Status),
  PolicyRequirement LABEL PolicyRequirement PROPERTIES (BundleId, Id, Status),
  ControlObjective LABEL ControlObjective PROPERTIES (BundleId, Id, Status),
  RiskType LABEL RiskType PROPERTIES (BundleId, Id, Status),
  RiskDriver LABEL RiskDriver PROPERTIES (BundleId, Id, Status)
)
EDGE TABLES (
  MandateAddressedBy
    SOURCE KEY (BundleId, SourceId) REFERENCES Mandate (BundleId, Id)
    DESTINATION KEY (BundleId, TargetId) REFERENCES PolicyRequirement (BundleId, Id)
    LABEL ADDRESSED_BY PROPERTIES (BundleId, Id, Status),
  PolicyImplementedBy
    SOURCE KEY (BundleId, SourceId) REFERENCES PolicyRequirement (BundleId, Id)
    DESTINATION KEY (BundleId, TargetId) REFERENCES ControlObjective (BundleId, Id)
    LABEL IMPLEMENTED_BY PROPERTIES (BundleId, Id, Status),
  MandateClassifiedAs
    SOURCE KEY (BundleId, SourceId) REFERENCES Mandate (BundleId, Id)
    DESTINATION KEY (BundleId, TargetId) REFERENCES RiskType (BundleId, Id)
    LABEL CLASSIFIED_AS PROPERTIES (BundleId, Id, Status),
  MandateDrivenBy
    SOURCE KEY (BundleId, SourceId) REFERENCES Mandate (BundleId, Id)
    DESTINATION KEY (BundleId, TargetId) REFERENCES RiskDriver (BundleId, Id)
    LABEL DRIVEN_BY PROPERTIES (BundleId, Id, Status)
);
