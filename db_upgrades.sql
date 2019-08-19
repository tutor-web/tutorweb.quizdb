-- 698d76d238223b18e794c8021b5e6158db82c0d8
ALTER TABLE question ADD incorrectChoices varchar(128) NOT NULL;

-- ef723f57bdd7b06885d74e013cf3ff0a33e61051
ALTER TABLE lecture ADD `currentVersion` int(11) NOT NULL;
ALTER TABLE question ADD `incorrectChoices` varchar(128) NOT NULL;
CREATE TABLE `lectureGlobalSetting` (
  `lectureId` int(11) NOT NULL,
  `lectureVersion` int(11) NOT NULL AUTO_INCREMENT,
  `key` varchar(100) COLLATE utf8_bin NOT NULL,
  `creationDate` datetime NOT NULL,
  `value` varchar(100) COLLATE utf8_bin DEFAULT NULL,
  `shape` float DEFAULT NULL,
  `max` float DEFAULT NULL,
  `min` float DEFAULT NULL,
  PRIMARY KEY (`lectureId`,`lectureVersion`,`key`),
  KEY `idx_autoinc_lectureVersion` (`lectureVersion`),
  CONSTRAINT `lectureGlobalSetting_ibfk_1` FOREIGN KEY (`lectureId`) REFERENCES `lecture` (`lectureId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
CREATE TABLE `lectureStudentSetting` (
  `lectureId` int(11) NOT NULL,
  `lectureVersion` int(11) NOT NULL,
  `studentId` int(11) NOT NULL,
  `key` varchar(100) COLLATE utf8_bin NOT NULL,
  `creationDate` datetime NOT NULL,
  `value` varchar(100) COLLATE utf8_bin NOT NULL,
  PRIMARY KEY (`lectureId`,`lectureVersion`,`studentId`,`key`),
  KEY `lectureVersion` (`lectureVersion`),
  KEY `studentId` (`studentId`),
  CONSTRAINT `lectureStudentSetting_ibfk_1`
    FOREIGN KEY (`lectureId`, `lectureVersion`)
    REFERENCES `lectureGlobalSetting` (`lectureId`, `lectureVersion`),
  CONSTRAINT `lectureStudentSetting_ibfk_2`
    FOREIGN KEY (`lectureId`)
    REFERENCES `lecture` (`lectureId`),
  CONSTRAINT `lectureStudentSetting_ibfk_3`
    FOREIGN KEY (`lectureVersion`)
    REFERENCES `lectureGlobalSetting` (`lectureVersion`),
  CONSTRAINT `lectureStudentSetting_ibfk_4`
    FOREIGN KEY (`studentId`)
    REFERENCES `student` (`studentId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8 COLLATE=utf8_bin;
ALTER TABLE answer ADD `lectureVersion` int(11) DEFAULT NULL;
ALTER TABLE answer ADD CONSTRAINT `answer_ibfk_x`
    FOREIGN KEY (`lectureId`, `lectureVersion`)
    REFERENCES `lectureGlobalSetting` (`lectureId`, `lectureVersion`);

-- b2f9572159b037b43c3e06ba02eab2aac6e615cf

ALTER TABLE lectureGlobalSetting
    ADD variant VARCHAR(100) NOT NULL DEFAULT "";
ALTER TABLE lectureGlobalSetting
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (`lectureId`,`lectureVersion`,`key`,`variant`);

-- f7bba547b306891585663f688ba1f65bdd486ef8

ALTER TABLE lectureStudentSetting
    ADD variant VARCHAR(100) NOT NULL DEFAULT "";

-- 2019-01-18

ALTER TABLE host
    ADD comment VARCHAR(1024) NULL;
ALTER TABLE host DROP INDEX ix_host_fqdn;

-- 2019-08-12

ALTER TABLE question ADD `title` TEXT NULL;

-- 2019-08-19

ALTER TABLE lectureGlobalSetting MODIFY value VARCHAR(4096);
ALTER TABLE lectureStudentSetting MODIFY value VARCHAR(4096);
