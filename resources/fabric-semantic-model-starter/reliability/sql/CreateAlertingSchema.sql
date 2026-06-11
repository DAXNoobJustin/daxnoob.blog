/*
 Semantic Model Alerting System - Database Schema

 Target Database : Semantic Model Alerting System (Fabric SQL Database)
 Artifact ID     : <ALERTING_DB_ARTIFACT_ID>
 Server          : <your-fabric-sql-server>.database.fabric.microsoft.com,1433

 Run this script against the database to create the required objects.
 (Auth: ActiveDirectoryDefault via Go sqlcmd, or run it in the Fabric SQL query editor.)
 */
-- ============================================================================
-- Table: AlertLog
-- Tracks every alert action (Incident, Teams, Refresh) for cooldown management
-- ============================================================================
IF NOT EXISTS (
    SELECT
        1
    FROM
        sys.tables
    WHERE
        [name] = 'AlertLog'
        AND schema_id = SCHEMA_ID('dbo')
) BEGIN CREATE TABLE [dbo].[AlertLog] (
    AlertLogId INT IDENTITY(1, 1) NOT NULL,
    ItemId NVARCHAR(255) NOT NULL,
    ItemName NVARCHAR(500) NULL,
    AlertType NVARCHAR(100) NOT NULL,
    -- PerformanceDegradation | ErrorSpike | OneLakeSecurityError
    ActionType NVARCHAR(50) NOT NULL,
    -- Incident | Teams | Refresh
    IncidentLink NVARCHAR(1000) NULL,
    Details NVARCHAR(MAX) NULL,
    CreatedAt DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_AlertLog PRIMARY KEY CLUSTERED (AlertLogId)
);

END;

GO
    -- Index for fast cooldown lookups (ItemId + AlertType + ActionType + recent CreatedAt)
    IF NOT EXISTS (
        SELECT
            1
        FROM
            sys.indexes
        WHERE
            [name] = 'IX_AlertLog_Cooldown'
            AND object_id = OBJECT_ID('dbo.AlertLog')
    ) BEGIN CREATE NONCLUSTERED INDEX IX_AlertLog_Cooldown ON [dbo].[AlertLog] (ItemId, AlertType, ActionType, CreatedAt DESC);

END;

GO
    -- ============================================================================
    -- Stored Procedure: ClaimAlertSlot
    -- Atomically checks cooldown AND reserves a slot to prevent race conditions.
    -- Returns Claimed = 1 if this caller won the slot, 0 if another run already claimed it.
    -- The caller should only proceed with the alert action if Claimed = 1.
    -- ============================================================================
    CREATE
    OR ALTER PROCEDURE [dbo].[ClaimAlertSlot] @ItemId NVARCHAR(255),
    @ItemName NVARCHAR(500) = NULL,
    @AlertType NVARCHAR(100),
    @ActionType NVARCHAR(50),
    @CooldownMinutes INT = 60 AS BEGIN
SET
    NOCOUNT ON;

DECLARE @Claimed INT = 0;

BEGIN TRANSACTION;

IF NOT EXISTS (
    SELECT
        1
    FROM
        [dbo].[AlertLog] WITH (UPDLOCK, HOLDLOCK)
    WHERE
        ItemId = @ItemId
        AND AlertType = @AlertType
        AND ActionType = @ActionType
        AND CreatedAt > DATEADD(MINUTE, - @CooldownMinutes, SYSUTCDATETIME())
) BEGIN
INSERT INTO
    [dbo].[AlertLog] (ItemId, ItemName, AlertType, ActionType, Details)
VALUES
    (
        @ItemId,
        @ItemName,
        @AlertType,
        @ActionType,
        'PENDING'
    );

SET
    @Claimed = 1;

END COMMIT TRANSACTION;

SELECT
    @Claimed AS Claimed;

END;

GO
    -- ============================================================================
    -- Stored Procedure: UpdateAlertDetails
    -- Called after a successful alert action to fill in details on the PENDING row.
    -- ============================================================================
    CREATE
    OR ALTER PROCEDURE [dbo].[UpdateAlertDetails] @ItemId NVARCHAR(255),
    @AlertType NVARCHAR(100),
    @ActionType NVARCHAR(50),
    @IncidentLink NVARCHAR(1000) = NULL,
    @Details NVARCHAR(MAX) = NULL AS BEGIN
SET
    NOCOUNT ON;

UPDATE
    [dbo].[AlertLog]
SET
    IncidentLink = @IncidentLink,
    Details = @Details
WHERE
    AlertLogId = (
        SELECT
            TOP (1) AlertLogId
        FROM
            [dbo].[AlertLog]
        WHERE
            ItemId = @ItemId
            AND AlertType = @AlertType
            AND ActionType = @ActionType
            AND Details = 'PENDING'
        ORDER BY
            AlertLogId DESC
    );

END;

GO
