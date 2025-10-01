package com.example.jitlab.api.storage;

import com.mongodb.client.gridfs.model.GridFSFile;
import org.bson.types.ObjectId;
import org.springframework.data.mongodb.gridfs.GridFsResource;
import org.springframework.data.mongodb.gridfs.GridFsTemplate;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

import java.io.IOException;

import static org.springframework.data.mongodb.core.query.Criteria.where;
import static org.springframework.data.mongodb.core.query.Query.query;

@Service
public class GridFsVideoService {
    private final GridFsTemplate gridFsTemplate;

    public GridFsVideoService(GridFsTemplate gridFsTemplate) {
        this.gridFsTemplate = gridFsTemplate;
    }

    public String save(MultipartFile file) throws IOException {
        ObjectId id = gridFsTemplate.store(
                file.getInputStream(),
                file.getOriginalFilename(),
                file.getContentType()
        );
        return id.toHexString();
    }

    public GridFsResource load(String id) {
        GridFSFile file = gridFsTemplate.findOne(query(where("_id").is(new ObjectId(id))));
        if (file == null) return null;
        return gridFsTemplate.getResource(file);
    }
}
