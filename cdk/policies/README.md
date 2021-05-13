# IMA policies for CDK deploy
Restrictive IAM Policies for AWS CDK

These are IAM policies that attempt to minimize the permissions required to perform a Domino deployment.

### IAM Role restrictions

Trust relationship in IAM role should be limited so this role can only be assumed by 
CloudFormation or EKS. No particular user should be 

```
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Service": [
          "cloudformation.amazonaws.com",
          "eks.amazonaws.com"
        ]
      },
      "Action": "sts:AssumeRole"
    }
  ]
}
```

### To be used with CDK
minimal_permissions_for_cdk_deploy_and_destroy.json

### To be used with CloudFormation UI and terraform
minimal_permissions_for_cf_ui_and_terraform.json

The reason for these two files being different is the fact that CDK is using CF API 
and almost all operations are supplied with the value CalledVia=cloudformation.
But CloudFormation UI (and terraform) somehow manage to do most of the operations
without setting this value, therefore these permissions are more relaxed.

Fortunately, some operations are still performed via CloudFormation. E.g. creation of EFS. 

## Template placeholders
* <YOUR_ACCOUNT>: AWS account ID in a form 87654321
* <YOUR_STACK_NAME>: Your stack name as in config.yaml name: field, e.g. my-stack-3. 
  During deploy is can become a 
  prefix in the generated names (ie "my-stack-3-state-machine")

You can subst values with sed. E.g.
```
sed -e "s/<YOUR_ACCOUNT>/87654321/g" -e "s/<YOUR_STACK_NAME>/my-stack-3/g" minimal_permissions_for_cdk_deploy_and_destroy.json
```